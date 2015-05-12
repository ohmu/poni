"""
command-line tool

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""
from __future__ import print_function
from . import cloud
from . import colors
from . import config
from . import core
from . import errors
from . import importer
from . import listout
from . import rcontrol_all
from . import template
from . import times
from . import util
from . import vc
from . import version
from . import work
from distutils.version import LooseVersion  # pylint: disable=E0611
import argh
import argparse
import glob
import itertools
import logging
import os
import re
import shlex
import shutil
import stat
import sys
import time

try:
    from argh import expects_obj
except ImportError:
    # older argh version
    expects_obj = lambda m: m

# suppress argh warnings about installing 'argcomplete'
import warnings
warnings.filterwarnings("ignore", ".*", Warning, "argh.completion")

try:
    from argh import named as argh_named
except ImportError:
    from argh import alias as argh_named  # pylint: disable=E0611


TOOL_NAME = "poni"

def arg_flag(*args, **kwargs):
    return argh.arg(*args, default=False, action="store_true", **kwargs)

# common arguments
arg_full_match = arg_flag("-M", "--full-match", dest="full_match",
                          help="require full regexp match")
arg_nodes_only = arg_flag("-N", "--nodes", dest="nodes_only",
                          help="apply only to nodes (not systems)")
arg_systems_only = arg_flag("-S", "--systems", dest="systems_only",
                          help="apply only to systems (not nodes)")
arg_verbose = arg_flag("-v", "--verbose", help="verbose output")
arg_quiet = arg_flag("-q", "--quiet", help="do not show remote command output")
arg_path_prefix = argh.arg('--path-prefix', type=str, default="",
                           help='additional prefix for all deployed files')
arg_exclude_nodes = argh.arg('--exclude', type=str,
                             metavar="PATTERN", help='exclude node pattern')
def arg_target_nodes_0_to_n(method):
    b = argh.arg('nodes', type=str, help='target nodes (regexp)', nargs="?")
    return arg_exclude_nodes(b(method))

def arg_target_nodes(method):
    b = argh.arg('nodes', type=str, help='target nodes (regexp)')
    return arg_exclude_nodes(b(method))

arg_host_access_method = argh.arg("-m", "--method",
                                  help="override host access method (local, ssh, tar:DIR)")
arg_output_dir = argh.arg("-o", "--output-dir", metavar="DIR",
                          help="write command output to files in DIR")
arg_config_pattern = argh.arg("-c", "--config", metavar="PATTERN", type=str, nargs="*",
                              help='apply to only configs matching pattern')
arg_tag = argh.arg("-t", "--tag", metavar="TAG", type=str,
                   help='apply to only files that are labeled with the specified tag')


class ControlTask(work.Task):
    def __init__(self, op, args, verbose=False, method=None, quiet=False,
                 output_dir=None, color="auto"):
        work.Task.__init__(self)
        self.op = op
        self.args = args
        self.verbose = verbose
        self.method = method
        self.quiet = quiet
        self.output_dir = output_dir
        self.color = color

    def __repr__(self):
        return "%s/%s [%s]" % (self.op["node"].name, self.op["config"].name,
                               self.op["name"])

    def send_output(self, msg):
        # TODO: label each output line
        self.log.info("%s: %s", self, msg)

    def can_start(self):
        """return True when it is ok to start this task"""
        host = self.op["node"].get("host")
        for running_task in self.runner.started:
            if running_task.op["node"].get("host") == host:
                # another task is already running on the same host
                return False

        for dep_op in self.op.get("depends", []):
            if not "result" in dep_op:
                # dependency task has not finished yet
                return False

        return True

    def check_dependencies(self):
        for dep_op in self.op.get("depends", []):
            if dep_op["result"]:
                # dependency task has failed, cannot continue
                dep_name = "%s/%s [%s]" % (dep_op["node"].name,
                                           dep_op["config"].name,
                                           dep_op["name"])

                raise errors.ControlError("dependency task %s failed" % (
                        dep_name))

    def execute(self):
        try:
            self.op["start_time"] = time.time()
            self.check_dependencies()
            handler_func = self.op["callback"]
            ret = handler_func(self.op["name"], self.args,
                               node=self.op["node"],
                               verbose=self.verbose,
                               quiet=self.quiet,
                               output_dir=self.output_dir,
                               method=self.method,
                               color=self.color,
                               send_output=self.send_output)
            self.log.debug("op %s returns: %r", self.op["name"], ret)
            self.op["result"] = ret
        except (SystemExit, errors.Error) as error:
            # SystemExit is what argh produces with invalid args
            self.log.error("%s/%s [%s] failed: %s: %s",
                    self.op["node"].name, self.op["config"].name,
                    self.op["name"], error.__class__.__name__, error)
            self.op["result"] = "%s: %s" % (error.__class__.__name__, error)
        except BaseException as error:
            self.log.error("%s/%s [%s] failed: %s: %s",
                    self.op["node"].name, self.op["config"].name,
                    self.op["name"], error.__class__.__name__, error)
            self.op["result"] = "Unhandled error: %s: %s" % (
                error.__class__.__name__, error)
            self.log.exception("task exception")
            raise
        finally:
            self.op["stop_time"] = time.time()


class Tool(object):
    """command-line tool"""
    def __init__(self, default_repo_path=None):
        self.log = logging.getLogger(TOOL_NAME)
        self.default_repo_path = default_repo_path
        self.sky = cloud.Sky()
        self.parser = self.create_parser()
        self.task_times = times.Times()
        self.cached_confman = None
        self.cached_manager = None
        self.collect_cache = {}

    def reset_cache(self):
        if self.cached_confman:
            self.cached_confman.reset_cache()

        self.cached_manager = None
        self.collect_cache = {}

    @argh_named("add-system")
    @argh.arg('system', type=str, help='system name')
    @expects_obj
    def handle_add_system(self, arg):
        """add a sub-system"""
        confman = self.get_confman(arg.root_dir)
        system_dir = confman.create_system(arg.system)
        self.log.debug("created: %s", system_dir)

    @argh_named("version")
    @expects_obj
    def handle_version(self, arg):
        """show version information"""
        yield version.__version__
        yield "\n"

    @argh_named("require")
    @arg_verbose
    @argh.arg("req", help="requirement expression (Python)", nargs="+")
    @expects_obj
    def handle_require(self, arg):
        """
        validate requirement expressions
        """
        props = {
            "poni_version": LooseVersion(version.__version__),
            }
        for req in arg.req:
            try:
                result = eval(req, {}, props)  # pylint: disable=W0123
                if arg.verbose:
                    self.log.info("requirement OK: %r", req)
            except Exception as error:
                raise errors.RequirementError("%s: %s: %s" % (
                        req, error.__class__.__name__, error))

            if not result:
                raise errors.RequirementError(
                    "requirement not met: %r" % req)

    @argh_named("init")
    @expects_obj
    def handle_init(self, arg):
        """init repository"""
        confman = self.get_confman(arg.root_dir, must_exist=False)
        confman.init_repo()

    @argh_named("import")
    @arg_verbose
    @argh.arg('source', help='source dir/file', nargs="+")
    @expects_obj
    def handle_import(self, arg):
        """import nodes/configs"""
        confman = self.get_confman(arg.root_dir)
        for glob_pattern in arg.source:
            sources = glob.glob(glob_pattern)
            if not sources:
                raise errors.UserError(
                    "'%s' does not match any files or directories" % (
                        glob_pattern))

            for source_path in sources:
                # TODO: move code to core.py
                source = importer.get_importer(source_path,
                                               verbose=arg.verbose)
                source.import_to(confman)

    def preprocess_script_lines(self, lines):
        i = 1
        lines = lines[:]
        while i < len(lines):
            if lines[i][:1].isspace():
                # needs to be catenated to previous line
                lines[i - 1] += "\n" + lines[i]
                del lines[i]
            else:
                i += 1

        return lines

    @argh_named("script")
    @arg_verbose
    @argh.arg('script', metavar="FILE", type=str,
              help='script file path or "-" (a single minus-sign) for stdin')
    @argh.arg('variable', type=str, nargs="*", help="'name=[type:]value'")
    @expects_obj
    def handle_script(self, arg):
        """run commands from a script file"""
        try:
            if arg.script != "-":
                script_text = open(arg.script).read()
            else:
                script_text = sys.stdin.read()
        except (OSError, IOError) as error:
            raise errors.Error("%s: %s" % (error.__class__.__name__, error))

        variables = dict(util.parse_prop(var) for var in arg.variable)
        variables['current_script_dir'] = os.path.dirname(arg.script)

        match = re.search(r"^\s*#\s+poni\.template\s*:\s*(\w+)", script_text, re.MULTILINE)
        engine = match.group(1) if match else "cheetah"
        script_text = template.render(engine=engine, source_text=script_text, variables=variables)
        lines = script_text.splitlines()

        def wrap(args):
            if " " in args:
                return repr(args)
            else:
                return args

        def set_repo_path(sub_arg):
            self.tune_arg_namespace(sub_arg)
            sub_arg.root_dir = arg.root_dir

        lines = self.preprocess_script_lines(lines)

        for i, line in enumerate(lines):
            args = shlex.split(line, comments=True)
            if not args:
                continue

            if arg.verbose:
                print("$ " + " ".join(wrap(a) for a in args))

            # strip arguments following "--"
            # TODO: this code is now in two places, refactor
            namespace = argparse.Namespace()
            try:
                extra_loc = args.index("--")
                namespace.extras = args[extra_loc + 1:]
                args = args[:extra_loc]
            except ValueError:
                namespace.extras = []

            start = time.time()
            self.parser.dispatch(argv=args, pre_call=set_repo_path,
                                 namespace=namespace)
            stop = time.time()
            if namespace.time_op:  # pylint: disable=E1101
                self.task_times.add_task("L%d" % (i + 1), line, start, stop, args=args)

    @argh_named("update-config")
    @arg_verbose
    @argh.arg('config', type=str, help="target config (regexp)")
    @argh.arg('source', help='source file or directory', nargs="+")
    @expects_obj
    def handle_update_config(self, arg):
        """update files to a config"""
        confman = self.get_confman(arg.root_dir)
        configs = list(confman.find_config(arg.config))
        if not configs:
            raise errors.UserError("no config matching %r found" % arg.config)

        for source_path in arg.source:
            for conf_node, conf in configs:
                if arg.verbose:
                    self.log.info("%s: added %r", conf.full_name,
                                  str(source_path))
                if os.path.isfile(source_path):
                    shutil.copy2(source_path, conf.path)
                elif os.path.isdir(source_path):
                    assert 0, "unimplemented"
                else:
                    raise errors.UserError("don't know how to handle: %r (cwd: %s)" %
                                           (str(source_path), os.getcwd()))

    @argh_named("remove-config")
    @arg_verbose
    @arg_full_match
    @arg_target_nodes
    @argh.arg('config', type=str, help='name of the config')
    @arg_flag("-e", "--skip-non-existing", help="do nothing if the config does not exist")
    @expects_obj
    def handle_remove_config(self, arg):
        """remove config from node(s)"""
        alog = self.log.info if arg.verbose else self.log.debug
        deletes = []
        confman = self.get_confman(arg.root_dir)
        nodes = confman.find(arg.nodes, full_match=arg.full_match, exclude=arg.exclude)
        for node in nodes:
            existing = list(c for c in node.iter_configs()
                            if c.name == arg.config)
            deletes.append("%s/%s" % (node.name, arg.config))
            if not existing:
                if arg.skip_non_existing:
                    self.log.info("config '%s/%s' does not exist, skipped",
                                  node.name, arg.config)
                    continue
                raise errors.UserError("config '%s/%s' does not exist"
                                       % (node.name, arg.config))

            node.remove_config(arg.config)
            alog("removed config %r from %s", arg.config, node.path)

        if not deletes and not arg.skip_non_existing:
            raise errors.UserError("no matching nodes found")

    @argh_named("add-config")
    @arg_verbose
    @arg_full_match
    @arg_target_nodes
    @argh.arg('config', type=str, help='name of the config')
    @argh.arg("-i", "--inherit", metavar="CONFIG", type=str, default="",
              dest="inherit_config", help="inherit from config (regexp)")
    @argh.arg("-d", "--copy-dir", metavar="DIR", type=str, default="",
              dest="copy_dir", help="copy config files from DIR")
    @arg_flag("-c", "--create-node", help="create node if it does not exist")
    @arg_flag("-e", "--skip-existing", help="do nothing if the config already exists")
    @expects_obj
    def handle_add_config(self, arg):
        """add a config to node(s)"""
        alog = self.log.info if arg.verbose else self.log.debug
        confman = self.get_confman(arg.root_dir)
        if arg.inherit_config:
            conf_node, conf = list(confman.get_config(arg.inherit_config))
            parent_config_name = "%s/%s" % (conf_node.name, conf.name)
            self.log.debug("parent config: node=%r, config=%r",
                           conf_node.name, parent_config_name)
        else:
            parent_config_name = None

        updates = []
        nodes = list(confman.find(arg.nodes, full_match=arg.full_match,
                                  exclude=arg.exclude))
        if arg.create_node and (not nodes):
            # node does not exist, create it as requested
            confman.create_node(arg.nodes)
            nodes = confman.find(arg.nodes, full_match=True,
                                 exclude=arg.exclude)

        for node in nodes:
            existing = list(c for c in node.iter_configs()
                            if c.name == arg.config)
            updates.append("%s/%s" % (node.name, arg.config))
            if existing:
                if arg.skip_existing:
                    self.log.info("config '%s/%s' already exists, skipped",
                                  node.name, arg.config)
                    continue
                else:
                    raise errors.UserError("config '%s/%s' already exists" % (
                            node.name, arg.config))

            node.add_config(arg.config, parent=parent_config_name,
                            copy_dir=arg.copy_dir)
            alog("added config %r to %s, parent=%r",
                 arg.config, node.path, parent_config_name)

        if not updates:
            raise errors.UserError("no matching nodes found")

    @argh_named("add-library")
    @arg_verbose
    @arg_full_match
    @argh.arg('-c', '--config', type=str, help='config search pattern')
    @argh.arg('name', type=str, help='library name')
    @argh.arg('path', help='library path within config')
    @expects_obj
    def handle_add_library(self, arg):
        """add a Python library from a config to PYTHONPATH"""
        confman = self.get_confman(arg.root_dir)

        if arg.config:
            # path is relative to a config
            configs = list(confman.find_config(arg.config))
            if not configs:
                raise errors.UserError(
                    "no config matching %r found" % arg.config)
            elif len(configs) > 1:
                raise errors.UserError(
                    "%r matched more than one config: %s" % (
                        arg.config, ", ".join(("%s/%s" % (n.name, c.name))
                                              for n, c in configs)))

            node, conf = configs[0]
            full_path = os.path.join(conf.path, arg.path)
            store_path = os.path.relpath(full_path, start=confman.root_dir)
        else:
            # arbitrary system dir path
            full_path = os.path.abspath(arg.path)
            store_path = full_path

        if not os.path.isdir(full_path):
            raise errors.UserError("directory %r does not exist" % (
                    str(full_path)))

        if os.path.isabs(store_path):
            self.log.warning("absolute Python library path to %r stored, "
                             "this may compromise repository portability",
                             str(store_path))

        confman.set_library_path(arg.name, store_path)
        logger = self.log.info if arg.verbose else self.log.debug
        logger("library %r path set: %s", arg.name, str(store_path))

    @argh_named("control")
    @arg_verbose
    @arg_full_match
    @arg_flag("-n", "--no-deps", help="do not run dependency tasks")
    @arg_flag("-i", "--ignore-missing",
              help="do not fail in case no matching operations are found")
    @arg_quiet
    @arg_output_dir
    @arg_flag("-t", "--clock-tasks", dest="show_times",
              help="show timeline of execution for each tasks")
    @argh.arg("-j", "--jobs", metavar="N", type=int,
              help="max concurrent tasks (default: unlimited)")
    @argh.arg('pattern', type=str, help='config search pattern')
    @arg_host_access_method
    @argh.arg('operation', type=str, help='operation to execute')
    @expects_obj
    def handle_control(self, arg):
        """config control operation"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        manager = self.get_manager(confman)
        self.collect_all(manager)

        # collect all possible control operations
        all_configs = list(confman.find_config(".", all_configs=True))
        all_ops = []
        provider = {}
        for conf_node, conf in all_configs:
            plugin = conf.get_plugin()
            if not plugin:
                # skip pluginless configs
                self.log.debug("skipping pluginless: %s:%s", conf_node.name,
                               conf.name)
                continue
            elif conf_node.get_tree_property("template", False):
                # skip template nodes
                self.log.debug("skipping template node: %s:%s", conf_node.name,
                               conf.name)
                continue

            for op in plugin.iter_control_operations(conf_node, conf):
                all_ops.append(op)
                for feature in op["provides"]:
                    ops = provider.setdefault(feature, [])
                    ops.append(op)

        handled = set()

        def add_all_required_ops(op):
            key = (op["node"].name, op["config"].name, op["name"])
            if key in handled:
                return
            handled.add(key)

            node = op["node"]
            conf = op["config"]
            tasks[(node.name, conf.name, op["name"])] = op

            reqs = [(True, req) for req in op["requires"]]
            reqs.extend((False, req) for req in op["optional_requires"])

            for must_have, feature in reqs:
                try:
                    provider_ops = provider[feature]
                except KeyError:
                    if not must_have:
                        # this feature is optional, missing provider is ok
                        continue

                    raise errors.OperationError(
                        "%s/%s operation %r depends on feature %r, "
                        "which is not provided by any config" % (
                        node.name, conf.name, arg.operation, feature))

                depends = op.setdefault("depends", [])
                for dep_op in provider_ops:
                    depends.append(dep_op)
                    add_all_required_ops(dep_op)

        # select user-specified ops and their dependencies from the full list
        tasks = {}
        comparison = core.ConfigMatch(arg.pattern, full_match=arg.full_match)
        for op in all_ops:
            node = op["node"]
            conf = op["config"]
            # control op name, node name, config name, all must match
            if ((arg.operation != op["name"])
                or not comparison.match_node(node.name)
                or not comparison.match_config(conf.name)):
                continue

            op["run"] = True  # only explicit targets are marked for running
            add_all_required_ops(op)

        if not tasks:
            if arg.ignore_missing:
                self.log.info("no matching operations found: --ignore-missing specified, ok!")
                return
            else:
                raise errors.UserError("no matching operations found")

        if arg.no_deps:
            # filter out the implicit dependency tasks
            for op in all_ops:
                depends = op.get("depends", [])
                for dep_op in depends[:]:
                    if not dep_op.get("run"):
                        depends.remove(dep_op)

        # assign tasks
        runner = work.Runner(max_jobs=arg.jobs)
        logger = self.log.info if arg.verbose else self.log.debug
        for op_id, op in tasks.items():
            run = op.get("run") or (not arg.no_deps)
            op["run"] = run
            if not run:
                continue

            plugin = op["plugin"]
            logger("scheduled to run: %s/%s [%s]", op["node"].name,
                   op["config"].name, op["name"])
            task = ControlTask(op, arg.extras, verbose=arg.verbose,
                               quiet=arg.quiet, output_dir=arg.output_dir,
                               method=arg.method, color=arg.color)
            runner.add_task(task)

        # execute tasks
        runner.run_all()

        # collect results
        results = [task.op.get("result") for task in runner.stopped]
        failed = [r for r in results if r]
        skipped_count = sum(1 for op in tasks.values() if not op["run"])
        ran_count = len(tasks) - skipped_count
        assert len(results) == ran_count

        # add task times to report
        for i, task in enumerate(runner.stopped):
            task_name = "%s/%s" % (task.op["node"].name,
                                   task.op["config"].name)
            self.task_times.add_task(i, task_name, task.op["start_time"],
                                     task.op["stop_time"])

        if arg.verbose:
            for task in runner.stopped:
                res = task.op["result"]
                if res:
                    self.log.error("FAILED: %s/%s [%s]: %r",
                                   task.op["node"].name,
                                   task.op["config"].name, task.op["name"],
                                   task.op["result"])

        self.log.debug("all tasks finished: %r", results)
        if failed:
            raise errors.ControlError(
                "[%d/%d] control tasks failed (%d skipped)" % (
                    len(failed), ran_count, skipped_count))
        else:
            self.log.info(
                "all [%d] control tasks finished successfully (%d skipped)",
                    ran_count, skipped_count)

    @argh_named("exec")
    @arg_verbose
    @arg_quiet
    @arg_output_dir
    @arg_full_match
    @arg_target_nodes
    @arg_host_access_method
    @argh.arg('cmd', type=str, help='command to execute')
    @expects_obj
    def handle_remote_exec(self, arg):
        """run a shell-command"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        def rexec(arg, node, remote):
            color = colors.Output(sys.stdout, color=arg.color).color
            if arg.output_dir:
                output_file_path = os.path.join(arg.output_dir, "%s.log" % node.name.replace("/", "_"))
                output_file = open(output_file_path, "w")
            else:
                output_file = None

            return remote.execute(arg.cmd, verbose=arg.verbose, color=color,
                                  quiet=arg.quiet,
                                  output_file=output_file)

        rexec.doc = "exec: %r" % arg.cmd
        result = self.remote_op(confman, arg, rexec, exclude=arg.exclude)
        if result:
            raise errors.RemoteError("remote exec failed with code: %r" % (
                    result,))

    @argh_named("cp")
    @arg_verbose
    @arg_full_match
    @arg_host_access_method
    @arg_flag("-d", "--create-dest-dir", help="create missing remote target directories")
    @arg_flag("-r", "--recursive", help="copy directories recursively")
    @argh.arg('source', type=str, nargs="+", help='source file/dir to copy')
    @arg_target_nodes
    @argh.arg('dest_dir', type=str, help='destination remote directory')
    @expects_obj
    def handle_remote_cp(self, arg):
        """copy file(s) to remote node(s)"""
        def pp(pth):
            """pretty-print paths to output-safe ascii"""
            return repr(str(pth))[1:-1]

        # sanity check
        for source in arg.source:
            try:
                st = os.stat(source)
                if not arg.recursive and stat.S_ISDIR(st.st_mode):
                    raise errors.UserError("copy source {0} is a directory and no -r specified".format(
                            pp(source)))

            except OSError as err:
                raise errors.UserError("invalid copy source {0}: {1.__class__.__name__}: {1}".format(  # pylint: disable=E1306
                        pp(source), err))

        def copy_file_or_dir(node, remote, source_path, dest_dir):
            try:
                remote.stat(dest_dir)
            except errors.RemoteError as err:
                if not "Errno 2" in str(err):
                    raise errors.UserError("{0}: unexpected error checking target directory {1}: {2.__class__.__name__}: {2}".format(  # pylint: disable=E1306
                            node.name, pp(dest_dir), err))
                elif not arg.create_dest_dir:
                    raise errors.UserError("{0}: Remote directory {1} does not exist. (use -d to create it)".format(
                            node.name, pp(dest_dir)))

                remote.makedirs(dest_dir)

            if os.path.isdir(source_path):
                source_paths = [os.path.join(source_path, name) for name in os.listdir(source_path)]
            else:
                source_paths = [source_path]
            for file_path in source_paths:
                dest_path = os.path.join(dest_dir, os.path.basename(file_path))
                lstat = os.lstat(file_path.stat)
                if stat.S_ISDIR(lstat.st_mode):
                    copy_file_or_dir(node, remote, os.path.join(source_path, os.path.basename(file_path)), dest_path)
                    continue

                if arg.verbose:
                    self.log.info("copying: %s -> %s:%s [%s]", pp(file_path), node.addr(), pp(dest_dir), node.name)
                remote.put_file(file_path, dest_path)
                remote.utime(dest_path, (int(lstat.st_mtime),
                                         int(lstat.st_mtime)))

        def copy_op(arg, node, remote):
            for source in arg.source:
                copy_file_or_dir(node, remote, source, arg.dest_dir)

        copy_op.doc = "cp"
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        self.remote_op(confman, arg, copy_op)

    @argh_named("shell")
    @arg_verbose
    @arg_full_match
    @arg_host_access_method
    @arg_target_nodes
    @expects_obj
    def handle_remote_shell(self, arg):
        """start an interactive shell session"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        color = colors.Output(sys.stdout, color=arg.color).color
        def rshell(arg, node, remote):
            remote.shell(verbose=arg.verbose, color=color)

        rshell.doc = "shell"
        self.remote_op(confman, arg, rshell)

    def remote_op(self, confman, arg, op, exclude=None):
        ret = 0
        nodes = list(confman.find(arg.nodes, full_match=arg.full_match,
                                  exclude=exclude))
        if not nodes:
            raise errors.UserError("%r does not match any nodes" % (arg.nodes))

        for node in nodes:
            if node.get_tree_property("template"):
                # don't try to run anything on template nodes
                continue

            remote = node.get_remote(override=arg.method)

            try:
                # TODO: pass color arg
                exit_code = op(arg, node, remote)
                if (not ret) and exit_code:
                    ret = exit_code
            except errors.RemoteError as error:
                self.log.error("failed: %s", error)
                ret = -1

        return ret

    @argh_named("init")
    @expects_obj
    def handle_vc_init(self, arg):
        """init version control in repo"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        if confman.vc:
            raise errors.UserError(
                "version control already initialized in this repo")

        confman.vc = vc.GitVersionControl(confman.root_dir, init=True)

    def require_vc(self, confman):
        if not confman.vc:
            raise errors.UserError(
                "version control not initialized in this repo")

    @argh_named("diff")
    @expects_obj
    def handle_vc_diff(self, arg):
        """show repository working status diff"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        self.require_vc(confman)
        for out in confman.vc.status():
            print(out.rstrip())

    @argh_named("checkpoint")
    @argh.arg('message', type=str, help='commit message')
    @expects_obj
    def handle_vc_checkpoint(self, arg):
        """commit all locally added and changed files in the repository"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        self.require_vc(confman)
        confman.vc.commit_all(arg.message)

    @argh_named("terminate")
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    @expects_obj
    def handle_cloud_terminate(self, arg):
        """terminate cloud instances"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        count = 0
        # group operations by provider
        clouds = {}
        for node in confman.find(arg.target, full_match=arg.full_match):
            cloud_prop = node.get("cloud", {})
            if cloud_prop.get("instance"):
                provider = self.sky.get_provider(cloud_prop)
                if provider not in clouds:
                    clouds[provider] = []
                clouds[provider].append(cloud_prop)
                self.log.info("terminating: %s", node.name)
        for provider, props in clouds.items():
            provider.terminate_instances(props)
            count += len(props)
        self.log.info("%s instances terminated", count)

    @argh_named("update")
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    @expects_obj
    def handle_cloud_update(self, arg):
        """update node cloud instance properties"""
        confman = self.get_confman(arg.root_dir)
        for node in confman.find(arg.target, full_match=arg.full_match):
            cloud_prop = node.get("cloud", {})
            if not cloud_prop.get("instance"):
                continue

            provider = self.sky.get_provider(cloud_prop)
            updates = provider.wait_instances([cloud_prop],
                                              wait_state=None)
            try:
                update = updates[cloud_prop["instance"]]
            except KeyError:
                raise errors.Error(
                    "TODO: did not get update from cloud provider for %r"
                    % cloud_prop["instance"])

            changes = node.log_update(update)
            if changes:
                change_str = ", ".join(("%s=%r (from %r)" % (c[0], c[2], c[1]))
                                       for c in changes)
                self.log.info("%s: updated: %s", node.name, change_str)
                node.save()

    @argh_named("wait")
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    @argh.arg('--state', type=str, default="running",
              help="target instance state, default: 'running'")
    @expects_obj
    def handle_cloud_wait(self, arg):
        """wait cloud instances to reach a specific running state"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        return self.cloud_op(confman, arg, False)

    @argh_named("init")
    @arg_full_match
    @argh.arg("target", type=str, help="target systems/nodes (regexp)")
    @arg_flag("--reinit", dest="reinit", help="re-initialize cloud image")
    @arg_flag("--wait", dest="wait", help="wait for instance to start")
    @expects_obj
    def handle_cloud_init(self, arg):
        """reserve and start a cloud instance for nodes"""
        confman = self.get_confman(arg.root_dir)
        return self.cloud_op(confman, arg, True)

    @argh_named("ip")
    @arg_full_match
    @argh.arg("target", type=str, help="target systems/nodes (regexp)")
    @expects_obj
    def handle_cloud_ip(self, arg):
        """assign ips to instances based on properties"""
        confman = core.ConfigMan(arg.root_dir)
        props = [node["cloud"]
                 for node in confman.find(arg.target, full_match=arg.full_match)
                 if node.get("cloud", None)]
        for provider, props in itertools.groupby(props, self.sky.get_provider):
            provider.assign_ip(props)

    def cloud_op(self, confman, arg, start):
        nodes = []

        def printable(dict_obj):
            return ", ".join(("%s=%r" % item) for item in dict_obj.items())

        for node in confman.find(arg.target, full_match=arg.full_match):
            cloud_prop = node.get("cloud", {})
            if not cloud_prop:
                continue

            if start and cloud_prop and cloud_prop.get("instance"):
                if not arg.reinit:
                    self.log.warning("%s has already been cloud-initialized, "
                                     "use --reinit to override",
                                     node.name)
                    continue
                else:
                    self.log.info("%s: reinit: existing config scrapped: %s",
                                  node.name, cloud_prop)

            if start:
                provider = self.sky.get_provider(cloud_prop)
                props = provider.init_instance(cloud_prop)
                node.update(props)
                node.save()
                self.log.info("%s: initialized: %s", node.name,
                              printable(props["cloud"]))
            nodes.append(node)

        if start:
            wait = arg.wait
            wait_state = "running"
        else:
            wait = True
            wait_state = arg.state

        if wait and nodes:
            # get unique "cloud" dicts from nodes
            uniq_props = set(util.hashed_dict(n["cloud"]) for n in nodes)
            providers = {}
            for cloud_prop in uniq_props:
                provider = self.sky.get_provider(cloud_prop)
                providers.setdefault(provider, []).append(cloud_prop)

            for provider, prop_list in providers.items():
                updates = provider.wait_instances(prop_list, wait_state=wait_state)

                for node in nodes:
                    instance_id = node.get("cloud", {}).get("instance")
                    if not instance_id:
                        raise errors.CloudError(
                            "cloud provider failed to set the 'instance' property for node '{0}'".format(
                                node.name))

                    update = updates.get(instance_id)

                    self.log.info("Check node: %s (id:%s) (upd:%s)", node, instance_id, update)
                    if not update:
                        raise errors.CloudError(
                            "cloud provider failed to return updated properties for node '{0}' (id:{1})".format(
                                node.name, instance_id))

                    changes = node.log_update(update)
                    if changes:
                        change_str = ", ".join(
                            ("%s=%r (from %r)" % (c[0], c[2], c[1]))
                            for c in changes)
                        self.log.info("%s: set: %s", node.name, change_str)
                        node.save()

    def _get_cloud_hosts_from_args(self, arg):
        confman = core.ConfigMan(arg.root_dir)
        props = [node["cloud"] for node in confman.find(arg.nodes, full_match=arg.full_match)
                 if node.get("cloud", None)]
        if not props:
            raise errors.UserError("%r does not match any nodes" % (arg.nodes))
        for provider, props in itertools.groupby(props, self.sky.get_provider):
            yield provider, props

    @argh_named("create-snapshot")
    @arg_full_match
    @arg_target_nodes
    @argh.arg("name", type=str, help="snapshot name")
    @argh.arg("--description", type=str, dest="description", default="", help="optional description of the snapshot")
    @arg_flag("--memory", dest="memory", help="include memory in the snapshot")
    @expects_obj
    def handle_cloud_create_snapshot(self, arg):
        """create a named snapshot for nodes"""
        for provider, props in self._get_cloud_hosts_from_args(arg):
            provider.create_snapshot(props, name=arg.name, description=arg.description, memory=arg.memory)

    @argh_named("revert-to-snapshot")
    @arg_full_match
    @arg_target_nodes
    @argh.arg("name", type=str, help="snapshot name")
    @expects_obj
    def handle_cloud_revert_to_snapshot(self, arg):
        """revert the nodes to a named snapshot"""
        for provider, props in self._get_cloud_hosts_from_args(arg):
            provider.revert_to_snapshot(props, name=arg.name)

    @argh_named("remove-snapshot")
    @arg_full_match
    @arg_target_nodes
    @argh.arg("name", type=str, help="snapshot name")
    @expects_obj
    def handle_cloud_remove_snapshot(self, arg):
        """remove a named snapshot from nodes"""
        for provider, props in self._get_cloud_hosts_from_args(arg):
            provider.remove_snapshot(props, name=arg.name)

    @argh_named("power-off")
    @arg_full_match
    @arg_target_nodes
    @expects_obj
    def handle_cloud_power_off(self, arg):
        """Power off nodes"""
        for provider, props in self._get_cloud_hosts_from_args(arg):
            provider.power_off_instances(props)

    @argh_named("power-on")
    @arg_full_match
    @arg_target_nodes
    @expects_obj
    def handle_cloud_power_on(self, arg):
        """Power on nodes"""
        for provider, props in self._get_cloud_hosts_from_args(arg):
            provider.power_on_instances(props)

    @argh_named("set")
    @arg_verbose
    @arg_full_match
    @arg_nodes_only
    @arg_systems_only
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    @argh.arg('property', type=str, nargs="+", help="'name=[type:]value'")
    @expects_obj
    def handle_set(self, arg):
        """set system/node properties"""
        confman = self.get_confman(arg.root_dir)
        logger = logging.info if arg.verbose else logging.debug
        changed_items = []
        found = False
        if arg.nodes_only:
            nodes = True
            systems = False
        elif arg.systems_only:
            nodes = False
            systems = True
        else:
            nodes = True
            systems = True

        for item in confman.find(arg.target, nodes=nodes, systems=systems,
                                 full_match=arg.full_match):
            found = True
            converters = {
                "prop": (
                    lambda x: util.get_dict_prop(dict(node=item), x.split("."),  # pylint: disable=W0631, W0640
                                                 verify=True)[1],
                    None
                    )
                }
            props = dict(util.parse_prop(p, converters=converters)
                         for p in arg.property)
            changes = item.set_properties(props)
            old_value = None
            for key, old_value, new_value in changes:
                changed = ((type(old_value) != type(new_value))  # pylint: disable=W1504
                           or (old_value != new_value))
                if changed:
                    note = "was %r" % old_value
                else:
                    note = "no change"

                logger("%s: set %s=%r (%s)", item.name, key, new_value, note)

            if not changes:
                logger("%s: no changes (%r)", item.name, old_value)
            else:
                changed_items.append(item)

        if not found:
            raise errors.Error("no matching nodes found")

        for item in changed_items:
            item.save()

    def collect_all(self, manager):
        items = self.collect_cache.get(manager)
        if items:
            return items

        items = []
        for item in manager.confman.find("."):
            item.collect(manager)
            items.append(item)

        # parents need to be collected _after_ all nodes have been collected,
        # so that every parent node is loaded and available with full props
        for item in items:
            item.collect_parents(manager)

        self.collect_cache[manager] = items

        return items

    def verify_op(self, confman, target, full_match=False, exclude=None,
                  **verify_options):
        manager = self.get_manager(confman)
        self.collect_all(manager)
        self.log.debug("verify_op %r: confman cache=%r, manager files=%r, buckets=%r",
                       target, confman.dump_stats(), len(manager.files),
                       dict((k, len(v)) for k, v in manager.buckets.items()))

        if target:
            if exclude:
                exclude = re.compile(exclude).search
            else:
                exclude = lambda name: False

            if full_match:
                search_op = re.compile(target + "$").match
            else:
                search_op = re.compile(target).search

            def target_filter(item):
                return (search_op(item["node"].name)
                        and not exclude(item["node"].name))
        else:
            target_filter = lambda item: True

        stats = manager.verify(callback=target_filter, **verify_options)
        return manager, stats

    @argh_named("show")
    @arg_verbose
    @arg_full_match
    @arg_target_nodes_0_to_n
    @arg_flag("-B", "--buckets", dest="show_buckets",
              help="show dynamic buckets")
    @arg_flag("--raw", dest="show_raw", help="show raw templates")
    @arg_flag("-d", "--diff", dest="show_diff",
              help="show raw template vs. rendered output diff")
    @arg_config_pattern
    @arg_tag
    @expects_obj
    def handle_show(self, arg):
        """render and show node config files"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        manager, stats = self.verify_op(
            confman, arg.nodes, show=(not arg.show_buckets),
            full_match=arg.full_match, raw=arg.show_raw,
            color=arg.color, show_diff=arg.show_diff,
            exclude=arg.exclude, config_patterns=arg.config,
            tag=arg.tag)

        if arg.show_buckets:
            for name, items in manager.buckets.items():
                for i, item in enumerate(items):
                    print("%s #%d: %r" % (name, i, item))

    @argh_named("report")
    @argh.arg("-o", "--output-file", metavar="FILE", nargs="?",
              help='output file path (default: stdout)')
    @expects_obj
    def handle_report(self, arg):
        """show command execution timeline report"""
        out = open(arg.output_file, "w") if arg.output_file else sys.stdout
        for chunk in self.task_times.iter_report():
            out.write(chunk)

    @argh_named("deploy")
    @arg_verbose
    @arg_full_match
    @arg_path_prefix
    @arg_target_nodes_0_to_n
    @arg_host_access_method
    @arg_config_pattern
    @arg_tag
    @expects_obj
    def handle_deploy(self, arg):
        """deploy node configs"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        manager, stats = self.verify_op(
            confman, arg.nodes, show=False, deploy=True, verbose=arg.verbose,
            full_match=arg.full_match, path_prefix=arg.path_prefix,
            access_method=arg.method, color=arg.color,
            exclude=arg.exclude, config_patterns=arg.config, tag=arg.tag)
        if stats.error_count:
            raise errors.VerifyError("failed: files with errors: [%d/%d]" % (
                    stats.error_count, stats.file_count))
        elif not stats.file_count:
            self.log.info("no files to deploy")
        else:
            self.log.info("all [%d] files ok", stats.file_count)

    @argh_named("audit")
    @arg_verbose
    @arg_full_match
    @arg_path_prefix
    @arg_target_nodes_0_to_n
    @arg_host_access_method
    @arg_flag("-d", "--diff", dest="show_diff", help="show config diffs")
    @arg_config_pattern
    @arg_tag
    @expects_obj
    def handle_audit(self, arg):
        """audit active node configs"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        manager, stats = self.verify_op(
            confman, arg.nodes, show=False, deploy=False, audit=True,
            show_diff=arg.show_diff, full_match=arg.full_match,
            path_prefix=arg.path_prefix, access_method=arg.method,
            color=arg.color, verbose=arg.verbose,
            exclude=arg.exclude, config_patterns=arg.config, tag=arg.tag)

        if stats.error_count:
            raise errors.VerifyError("failed: files with errors: [%d/%d]" % (
                    stats.error_count, stats.file_count))
        elif not stats.file_count:
            self.log.info("no files to audit")
        else:
            self.log.info("all [%d] files ok", stats.file_count)

    @argh_named("verify")
    @arg_verbose
    @arg_full_match
    @arg_host_access_method
    @arg_config_pattern
    @arg_tag
    @arg_target_nodes_0_to_n
    @expects_obj
    def handle_verify(self, arg):
        """verify local node configs"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        manager, stats = self.verify_op(
            confman, arg.nodes, show=False, full_match=arg.full_match,
            access_method=arg.method, verbose=arg.verbose,
            color=arg.color, exclude=arg.exclude, config_patterns=arg.config,
            tag=arg.tag)

        if stats.error_count:
            raise errors.VerifyError("failed: files with errors: [%d/%d]" % (
                    stats.error_count, stats.file_count))
        elif not stats.file_count:
            self.log.info("no files to verify")
        else:
            self.log.info("all [%d] files ok", stats.file_count)

    @argh_named("add-node")
    @arg_verbose
    @arg_full_match
    @argh.arg('node', type=str,
              help="name of the node, '{id}' is replaced with the node number")
    @argh.arg("-n", "--count", metavar="N..M", type=str, default="1",
              help="number of nodes ('N' or 'N..M')")
    @argh.arg("-H", "--host", metavar="HOST", type=str, default="",
              dest="host", help="host address")
    @argh.arg("-i", "--inherit-node", metavar="NODE", type=str, default="",
              dest="inherit_node", help="inherit from node (regexp)")
    @arg_flag("-c", "--copy-props", help="copy parent node's properties")
    @expects_obj
    def handle_add_node(self, arg):
        """add a new node"""
        confman = self.get_confman(arg.root_dir)
        if arg.inherit_node:
            nodes = list(confman.find(arg.inherit_node,
                                      full_match=arg.full_match))
            if len(nodes) == 0:
                raise errors.UserError(
                    "pattern %r does not match any nodes" % (arg.inherit_node))
            elif len(nodes) > 1:
                raise errors.UserError(
                    "pattern %r matches multiple nodes: %s" % (
                        arg.inherit_node, ", ".join(n.name for n in nodes)))

            parent_node_name = nodes[0].name
        else:
            parent_node_name = None

        if arg.verbose:
            logger = self.log.info
        else:
            logger = self.log.debug

        n, m = util.parse_count(arg.count)
        for n in range(n, m):
            node_name = arg.node.format(id=n)
            host = arg.host.format(id=n)
            confman.create_node(
                node_name, host=host, parent_node_name=parent_node_name,
                copy_props=arg.copy_props)

            if parent_node_name:
                msg = " <= %s" % (parent_node_name)
            else:
                msg = ""

            logger("node added: %s%s", node_name, msg)

    @argh_named("list")
    @arg_full_match
    @argh.arg('pattern', type=str, help='search pattern', nargs="?")
    @arg_exclude_nodes
    @arg_flag("-n", "--nodes", dest="show_nodes", help="show nodes")
    @arg_flag("-s", "--systems", dest="show_systems", help="show systems")
    @arg_flag("-c", "--config", dest="show_config", help="show node configs")
    @arg_flag("-P", "--config-prop", dest="show_config_prop",
              help="show node config properties")
    @arg_flag("-C", "--controls", dest="show_controls",
              help="show config control commands")
    @arg_flag("-t", "--tree", dest="show_tree", help="indented tree output")
    @arg_flag("-p", "--node-prop", dest="show_node_prop",
              help="show node properties")
    @arg_flag("-o", "--cloud", dest="show_cloud_prop",
              help="show node cloud properties")
    @arg_flag("-q", "--query-status", help="query and show cloud node status")
    @arg_flag("-i", "--inherits", dest="show_inherits",
              help="show node and config inheritances")
    @arg_flag("-l", "--line-per-prop", dest="list_props",
              help="one line per property")
    @expects_obj
    def handle_list(self, arg):
        """list systems and nodes"""
        confman = self.get_confman(arg.root_dir, reset_cache=False)

        manager = self.get_manager(confman)
        if arg.show_controls:
            self.collect_all(manager)

        list_output = listout.ListOutput(self, confman, **arg.__dict__)
        for output in list_output.output():
            yield output

    def get_confman(self, root_dir, must_exist=True, reset_cache=True):
        if reset_cache:
            self.reset_cache()

        if not self.cached_confman:
            self.cached_confman = core.ConfigMan(root_dir, must_exist=must_exist)

        return self.cached_confman

    def get_manager(self, confman):
        if self.cached_manager:
            #self.cached_manager.reset()
            pass
        else:
            self.cached_manager = config.Manager(confman)

        return self.cached_manager

    @argh_named("list")
    @arg_full_match
    @arg_flag("-l", "--show-layers", help="show settings layers")
    @argh.arg('pattern', type=str, help='node search pattern', nargs="?")
    @expects_obj
    def handle_settings_list(self, arg):
        """list settings"""
        pattern = arg.pattern or "."
        confman = self.get_confman(arg.root_dir, reset_cache=False)
        list_output = listout.ListOutput(self, confman, show_settings=True,
                                         show_config=True, **arg.__dict__)
        for output in list_output.output():
            yield output

    @argh_named("set")
    @arg_full_match
    @argh.arg('pattern', type=str, help='search pattern')
    @argh.arg('setting', type=str, nargs="+", help="'name=[type:]value'")
    @expects_obj
    def handle_settings_set(self, arg):
        """override settings values"""
        pattern = arg.pattern or "."
        confman = self.get_confman(arg.root_dir)
        configs = list(confman.find_config(arg.pattern, all_configs=True,
                                           full_match=arg.full_match))
        if not configs:
            raise errors.UserError("no config matching %r found" % arg.pattern)

        # verify all updates first, collect them to a list
        updates = []
        for conf_node, conf in configs:
            if conf_node != conf.node:
                # TODO: 1. add-config CONF -i orignode/CONF 2. apply changes
                raise errors.UserError("changing settings in a node-inherited "
                                       "config is not supported yet")

            set_list = []
            converters = {
                "prop": (
                    lambda x: util.get_dict_prop(dict(node=conf_node,  # pylint: disable=W0640
                                                      config=conf),  # pylint: disable=W0631, W0640
                                                 x.split("."),
                                                 verify=True)[1],
                    None
                    )
                }
            props = dict(util.parse_prop(p, converters=converters)
                         for p in arg.setting)
            for key_path, value in props.items():
                addr = key_path.split(".")
                old = util.set_dict_prop(conf.settings, addr, value,
                                         verify=True)
                if old != value:
                    # needs to be set
                    set_list.append((addr, value))
                else:
                    # TODO: must be set anyway (in case default changes!)
                    self.log.info("%s/%s: %r: no change", conf_node.name,
                                  conf.name, ".".join(addr))

            if set_list:
                updates.append((conf, set_list))

        # apply updates
        layer_file = "50-user.json"
        for conf, update in updates:
            layer = conf.load_settings_layer(layer_file)
            for addr, value in update:
                self.log.info("%s: set %s to %r", conf.full_name,
                              ".".join(addr), value)
                addr[-1] = "!%s" % addr[-1]
                util.set_dict_prop(layer, addr, value, schema=conf.settings)

            conf.save_settings_layer(layer_file, layer)

    def create_parser(self):
        default_root = self.default_repo_path
        if not default_root:
            default_root = os.environ.get("%s_ROOT" % TOOL_NAME.upper())

        if not default_root:
            default_root = os.path.join(os.environ["HOME"], ".%s" % TOOL_NAME, "default")

        parser = argh.ArghParser()
        parser.add_argument("-E", "--pass-thru-exceptions", default=False,
                            action="store_true", help="do not suppress exceptions with user-friendly error messages")
        parser.add_argument("-D", "--debug", dest="debug", default=False,
                            action="store_true", help="enable debug output")
        parser.add_argument("-L", "--time-log", metavar="FILE",
                            help="update execution times to a file")
        parser.add_argument("-T", "--clock", metavar="NAME", dest="time_op",
                            help="time-log this operation as NAME")
        parser.add_argument(
            "-d", "--root-dir", dest="root_dir", default=default_root,
            type=os.path.abspath,
            metavar="DIR",
            help="repository root directory (default: $HOME/.poni/default)")
        parser.add_argument(
            "-c", "--color", default="auto",
            choices=["on", "off", "auto"], help="use color highlighting")

        commands = [
            self.handle_list, self.handle_add_system, self.handle_init,
            self.handle_import, self.handle_script, self.handle_add_config,
            self.handle_update_config, self.handle_remove_config,
            self.handle_control, self.handle_require, self.handle_add_library,
            self.handle_set, self.handle_show, self.handle_deploy,
            self.handle_audit, self.handle_verify, self.handle_add_node,
            self.handle_report, self.handle_version,
            ]
        commands.sort(key=lambda func: func.__name__)
        parser.add_commands(commands)

        parser.add_commands([
                self.handle_cloud_init, self.handle_cloud_terminate,
                self.handle_cloud_update, self.handle_cloud_wait,
                self.handle_cloud_ip,
                self.handle_cloud_create_snapshot,
                self.handle_cloud_revert_to_snapshot,
                self.handle_cloud_remove_snapshot,
                self.handle_cloud_power_off,
                self.handle_cloud_power_on,
                ],
                            namespace="cloud", title="cloud operations",
                            help="command to execute")

        parser.add_commands([
                self.handle_remote_exec, self.handle_remote_shell,
                self.handle_remote_cp,
                ],
                            namespace="remote", title="remote operations",
                            help="command to execute")

        parser.add_commands([
                self.handle_vc_init, self.handle_vc_diff,
                self.handle_vc_checkpoint,
                ],
                            namespace="vc", title="version-control operations",
                            help="command to execute")

        parser.add_commands([
                self.handle_settings_list, self.handle_settings_set,
                ],
                            namespace="settings",
                            title="config settings manipulation commands",
                            help="command to execute")

        return parser

    def tune_arg_namespace(self, arg):
        if arg.function == self.handle_list:
            # tune "list" arguments
            if arg.show_node_prop or arg.show_cloud_prop or arg.query_status:
                arg.show_nodes = True

            if arg.show_config_prop or arg.show_controls:
                arg.show_config = True

            if not any([arg.show_nodes, arg.show_systems, arg.show_config]):
                arg.show_nodes = True

            if arg.show_tree:
                if arg.show_config:
                    arg.show_nodes = True

                if arg.show_nodes:
                    arg.show_systems = True
        elif arg.function == self.handle_set:
            if arg.nodes_only and arg.systems_only:
                raise errors.UserError(
                    "cannot specify both --nodes and --systems")

    def run(self, args=None):
        def adjust_logging(arg):
            """tune the logging before executing commands"""
            self.tune_arg_namespace(arg)

            if arg.time_log and os.path.exists(arg.time_log):
                self.task_times.load(arg.time_log)

            if arg.debug:
                logging.getLogger().setLevel(logging.DEBUG)
            else:
                # paramiko is very talkative even at ERROR level...
                paramiko_logger = logging.getLogger('paramiko.transport')
                paramiko_logger.setLevel(logging.CRITICAL)

                # boto blabbers http errors at ERROR severity...
                boto_logger = logging.getLogger('boto')
                boto_logger.setLevel(logging.CRITICAL)

        # strip arguments following "--"
        args = args or sys.argv[1:]
        namespace = argparse.Namespace()
        try:
            extra_loc = args.index("--")
            namespace.extras = args[extra_loc + 1:]
            args = args[:extra_loc]
        except ValueError:
            namespace.extras = []

        try:
            start = time.time()
            exit_code = self.parser.dispatch(argv=args,
                                             pre_call=adjust_logging,
                                             raw_output=True,
                                             namespace=namespace)
            stop = time.time()
            if namespace.time_op:  # pylint: disable=E1101
                op_name = namespace.time_op if (namespace.time_op != "-") else (" ".join(args))  # pylint: disable=E1101
                self.task_times.add_task("C", op_name, start, stop, args=args)
        except KeyboardInterrupt:
            self.log.error("*** terminated by keyboard ***")
            if namespace.pass_thru_exceptions:  # pylint: disable=E1101
                raise
            return -1
        except errors.Error as error:
            self.log.error("%s: %s", error.__class__.__name__, error)
            if namespace.pass_thru_exceptions:  # pylint: disable=E1101
                raise
            return -1
        finally:
            if namespace.time_log:  # pylint: disable=E1101
                self.task_times.save(namespace.time_log)  # pylint: disable=E1101

            rcontrol_all.manager.cleanup()

        return exit_code

    def execute(self, args):
        exit_code = self.run(args)
        if exit_code:
            raise errors.UserError(
                "command %r failed with exit code %r" % (args, exit_code))
        return exit_code

    def main(self):
        """Setup logging and run a single command specified by sys.argv"""
        #format = "%(asctime)s\t%(threadName)s\t%(name)s\t%(levelname)s\t%(message)s"
        format_str = "%(name)s\t%(levelname)s\t%(message)s"
        logging.basicConfig(level=logging.INFO, format=format_str)
        return self.run()

    @classmethod
    def run_exit(cls):
        """Helper that can be called from setuptools 'console_scripts'"""
        sys.exit(cls().main() or 0)


if __name__ == "__main__":
    Tool().main()
