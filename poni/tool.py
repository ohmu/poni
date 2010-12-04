"""
command-line tool

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

import os
import re
import sys
import logging
import shlex
import argh
import glob
import shutil
from path import path
from . import config
from . import errors
from . import util
from . import core
from . import cloud
from . import vc
from . import importer
from . import colors

TOOL_NAME = "poni"


def arg_full_match(method):
    wrap = argh.arg("-M", "--full-match", default=False, dest="full_match",
                    action="store_true", help="require full regexp match")
    return wrap(method)


def arg_verbose(method):
    wrap = argh.arg("-v", "--verbose", default=False, action="store_true",
                    help="verbose output")
    return wrap(method)


def arg_flag(*args, **kwargs):
    return argh.arg(*args, default=False, action="store_true", **kwargs)


class Tool:
    """command-line tool"""
    def __init__(self, default_repo_path=None):
        self.log = logging.getLogger(TOOL_NAME)
        self.default_repo_path = default_repo_path
        self.sky = cloud.Sky()
        self.parser = self.create_parser()

    @argh.alias("add-system")
    @argh.arg('system', type=str, help='system name')
    def handle_add_system(self, arg):
        """add a sub-system"""
        confman = core.ConfigMan(arg.root_dir)
        system_dir = confman.create_system(arg.system)
        self.log.debug("created: %s", system_dir)

    @argh.alias("init")
    def handle_init(self, arg):
        """init repository"""
        confman = core.ConfigMan(arg.root_dir, must_exist=False)
        confman.init_repo()

    @argh.alias("import")
    @arg_verbose
    @argh.arg('source', type=path, help='source dir/file', nargs="+")
    def handle_import(self, arg):
        """import nodes/configs"""
        confman = core.ConfigMan(arg.root_dir)
        for glob_pattern in arg.source:
            for source_path in glob.glob(glob_pattern):
                source = importer.get_importer(source_path)
                source.import_to(confman, verbose=arg.verbose)

    @argh.alias("script")
    @arg_verbose
    @argh.arg('script', type=str, help='script file', nargs="?")
    def handle_script(self, arg):
        """run commands from a script file"""
        try:
            if arg.script:
                lines = file(arg.script).readlines()
            else:
                lines = sys.stdin.readlines()
        except (OSError, IOError), error:
            raise errors.Error("%s: %s" % (error.__class__.__name__, error))

        def wrap(args):
            if " " in args:
                return repr(args)
            else:
                return args

        def set_repo_path(sub_arg):
            sub_arg.root_dir = arg.root_dir

        for line in lines:
            args = shlex.split(line, comments=True)
            if not args:
                continue

            if arg.verbose:
                print "$ " + " ".join(wrap(a) for a in args)

            self.parser.dispatch(argv=args, pre_call=set_repo_path)

    @argh.alias("update-config")
    @arg_verbose
    @argh.arg('config', type=str, help="target config (regexp)")
    @argh.arg('source', type=path, help='source file or dir', nargs="+")
    def handle_update_config(self, arg):
        """update files to a config"""
        confman = core.ConfigMan(arg.root_dir)
        configs = list(confman.find_config(arg.config))
        if not configs:
            raise errors.UserError("no config matching %r found" % arg.config)

        for source_path in arg.source:
            for config in configs:
                if arg.verbose:
                    self.log.info("%s/%s: added %r", config.node.name,
                                  config.name, str(source_path))
                if source_path.isfile():
                    shutil.copy2(source_path, config.path)
                elif source_path.isdir():
                    assert 0, "unimplemented"
                else:
                    raise UserError("don't know how to handle: %r" %
                                    str(source_path))

    @argh.alias("add-config")
    @arg_verbose
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)')
    @argh.arg('config', type=str, help='name of the config')
    @argh.arg("-i", "--inherit", metavar="CONFIG", type=str, default="",
              dest="inherit_config", help="inherit from config (regexp)")
    @argh.arg("-d", "--copy-dir", metavar="DIR", type=str, default="",
              dest="copy_dir", help="copy config files from DIR")
    @arg_flag("-c", "--create-node", help="create node if it does not exist")
    def handle_add_config(self, arg):
        """add a config to node(s)"""
        confman = core.ConfigMan(arg.root_dir)
        if arg.inherit_config:
            configs = list(confman.find_config(arg.inherit_config))
            if len(configs) == 0:
                raise errors.UserError(
                    "pattern %r does not match any configs" % (
                        arg.inherit_config))
            elif len(configs) > 1:
                names = (("%s/%s" % (c.node.name, c.name))
                         for c in configs)
                raise errors.UserError(
                    "pattern %r matches multiple configs: %s" % (
                        arg.inherit_config, ", ".join(names)))
            else:
                conf = configs[0]

            parent_config_name = "%s/%s" % (conf.node.name, conf.name)
            self.log.debug("parent config: node=%r, config=%r",
                           conf.node.name, parent_config_name)
        else:
            parent_config_name = None

        updates = []
        nodes = list(confman.find(arg.nodes, full_match=arg.full_match))
        if arg.create_node and (not nodes):
            # node does not exist, create it as requested
            confman.create_node(arg.nodes)
            nodes = confman.find(arg.nodes, full_match=True)

        for node in nodes:
            existing = list(c for c in node.iter_configs()
                            if c.name == arg.config)
            if existing:
                raise errors.UserError("config '%s/%s' already exists" % (
                        node.name, arg.config))

            node.add_config(arg.config, parent=parent_config_name,
                            copy_dir=arg.copy_dir)
            # TODO: verbose output
            self.log.debug("added config %r to %s, parent=%r", arg.config,
                           node.path, parent_config_name)
            updates.append("%s/%s" % (node.name, arg.config))

        if not updates:
            self.log.error("no matching nodes found")
            return -1
        elif arg.verbose:
            self.log.info("config %r added to: %s", arg.config,
                          ", ".join(updates))

    @argh.alias("exec")
    @arg_verbose
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)')
    @argh.arg('cmd', type=str, help='command to execute')
    def handle_remote_exec(self, arg):
        """run a shell-command"""
        confman = core.ConfigMan(arg.root_dir)
        def rexec(arg, node, remote):
            return remote.execute(arg.cmd)

        rexec.doc = "exec: %r" % arg.cmd
        return self.remote_op(confman, arg, rexec)

    @argh.alias("shell")
    @arg_verbose
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)')
    def handle_remote_shell(self, arg):
        """start an interactive shell session"""
        confman = core.ConfigMan(arg.root_dir)
        def rshell(arg, node, remote):
            remote.shell()

        rshell.doc = "shell"
        self.remote_op(confman, arg, rshell)

    def remote_op(self, confman, arg, op):
        ret = 0
        for node in confman.find(arg.nodes, full_match=arg.full_match):
            if not node.get("host"):
                continue

            remote = node.get_remote()
            desc = "%s (%s): %s" % (node.name, node.get("host"), op.doc)
            if arg.verbose:
                print "--- BEGIN %s ---" % desc

            try:
                exit_code = op(arg, node, remote)
                if (not ret) and exit_code:
                    ret = exit_code
            except errors.RemoteError, error:
                self.log.error("failed: %s", error)
                ret = -1

            if arg.verbose:
                print "--- END %s ---" % desc
                print

        return ret

    def handle_control(self, arg):
        re_conf = re.compile(arg.configs)
        for node in self.confman.find(arg.nodes):
            for conf in node.iter_configs():
                if not re_conf.search(conf.name):
                    continue

                doc, controls = conf.get_controls()
                control_func = controls.get(arg.control)
                if control_func:
                    control_func()

    @argh.alias("init")
    def handle_vc_init(self, arg):
        """init version control in repo"""
        confman = core.ConfigMan(arg.root_dir)
        if confman.vc:
            raise errors.UserError(
                "version control already initialized in this repo")

        confman.vc = vc.GitVersionControl(confman.root_dir, init=True)

    def require_vc(self, confman):
        if not confman.vc:
            raise errors.UserError(
                "version control not initialized in this repo")

    @argh.alias("diff")
    def handle_vc_diff(self, arg):
        """show repository working status diff"""
        confman = core.ConfigMan(arg.root_dir)
        self.require_vc(confman)
        for out in confman.vc.status():
            print out,

    @argh.alias("checkpoint")
    @argh.arg('message', type=str, help='commit message')
    def handle_vc_checkpoint(self, arg):
        """commit all locally added and changed files in the repository"""
        confman = core.ConfigMan(arg.root_dir)
        self.require_vc(confman)
        confman.vc.commit_all(arg.message)

    @argh.alias("terminate")
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    def handle_cloud_terminate(self, arg):
        """terminate cloud instances"""
        confman = core.ConfigMan(arg.root_dir)
        count = 0
        for node in confman.find(arg.target, full_match=arg.full_match):
            cloud_prop = node.get("cloud", {})
            if cloud_prop.get("instance"):
                provider = self.sky.get_provider(cloud_prop)
                provider.terminate_instances([cloud_prop])
                self.log.info("terminated: %s", node.name)
                count += 1

        self.log.info("%s instances terminated", count)

    @argh.alias("update")
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    def handle_cloud_update(self, arg):
        """update node cloud instance properties"""
        confman = core.ConfigMan(arg.root_dir)
        nodes = []
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
                raise errors.Error("TODO: did not get update from cloud provider for %r" % cloud_prop["instance"])

            changes = node.log_update(update)
            if changes:
                change_str = ", ".join(("%s=%r (from %r)" % (c[0], c[2], c[1]))
                                       for c in changes)
                self.log.info("%s: updated: %s", node.name, change_str)
                node.save()

    @argh.alias("wait")
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    @argh.arg('--state', type=str, default="running",
              help="target instance state, default: 'running'")
    def handle_cloud_wait(self, arg):
        """wait cloud instances to reach a specific running state"""
        confman = core.ConfigMan(arg.root_dir)
        return self.cloud_op(confman, arg, False)

    @argh.alias("init")
    @arg_full_match
    @argh.arg("target", type=str, help="target systems/nodes (regexp)")
    @arg_flag("--reinit", dest="reinit", help="re-initialize cloud image")
    @arg_flag("--wait", dest="wait", help="wait for instance to start")
    def handle_cloud_init(self, arg):
        """reserve and start a cloud instance for nodes"""
        confman = core.ConfigMan(arg.root_dir)
        return self.cloud_op(confman, arg, True)

    def cloud_op(self, confman, arg, start):
        nodes = []

        def printable(dict_obj):
            return ", ".join(("%s=%r" % item) for item in dict_obj.iteritems())

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
            props = [n["cloud"] for n in nodes]
            providers = {}
            for cloud_prop in props:
                provider = self.sky.get_provider(cloud_prop)
                prop_list = providers.setdefault(provider, [])
                prop_list.append(cloud_prop)

            for provider, prop_list in providers.iteritems():
                updates = provider.wait_instances(props, wait_state=wait_state)

                for node in nodes:
                    node_update = updates[node["cloud"]["instance"]]

                    changes = node.log_update(node_update)
                    if changes:
                        change_str = ", ".join(
                            ("%s=%r (from %r)" % (c[0], c[2], c[1]))
                            for c in changes)
                        self.log.info("%s: updated: %s", node.name, change_str)
                        node.save()

                    #node.update(node_update)
                    #node.save()
                    #self.log.info("%s update: %s", node.name,
                    #              printable(node_update))

    @argh.alias("set")
    @arg_verbose
    @arg_full_match
    @argh.arg('target', type=str, help='target systems/nodes (regexp)')
    @argh.arg('property', type=str, nargs="+", help="'name=[type:]value'")
    def handle_set(self, arg):
        """set system/node properties"""
        confman = core.ConfigMan(arg.root_dir)
        props = dict(util.parse_prop(p) for p in arg.property)
        logger = logging.info if arg.verbose else logging.debug
        changed_items = []
        found = False
        for item in confman.find(arg.target, systems=True,
                                 full_match=arg.full_match):
            found = True
            changes = item.set_properties(props)
            for key, old_value, new_value in changes:
                logger("%s: set %s=%r (was %r)", item.name, key, new_value,
                       old_value)

            if not changes:
                logger("%s: no changes", item.name)
            else:
                changed_items.append(item)

        if not found:
            raise errors.Error("no matching nodes found")

        for item in changed_items:
            item.save()

    def collect_all(self, manager):
        items = []
        for item in manager.confman.find("."):
            item.collect(manager)
            items.append(item)

        # parents need to be collected _after_ all nodes have been collected,
        # so that every parent node is loaded and available with full props
        for item in items:
            item.collect_parents(manager)

        return items

    def verify_op(self, confman, target, full_match=False, **verify_options):
        manager = config.Manager(confman)
        self.collect_all(manager)

        if target:
            if full_match:
                search_op = re.compile(target + "$").match
            else:
                search_op = re.compile(target).search

            def target_filter(item):
                return re_target.search(item["node"].name)
        else:
            target_filter = lambda item: True

        manager.verify(callback=target_filter, **verify_options)
        return manager

    @argh.alias("show")
    @arg_verbose
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)', nargs="?")
    @arg_flag("-d", "--show-dynamic", dest="show_dynamic",
              help="show dynamic configuration")
    def handle_show(self, arg):
        """render and show node config files"""
        confman = core.ConfigMan(arg.root_dir)
        manager = self.verify_op(confman, arg.nodes,
                                 show=(not arg.show_dynamic),
                                 full_match=arg.full_match)
        if arg.show_dynamic:
            for item in manager.dynamic_conf:
                print item

    @argh.alias("deploy")
    @arg_verbose
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)', nargs="?")
    def handle_deploy(self, arg):
        """deploy node configs"""
        confman = core.ConfigMan(arg.root_dir)
        self.verify_op(confman, arg.nodes, show=False, deploy=True,
                       verbose=arg.verbose, full_match=arg.full_match)

    @argh.alias("audit")
    @arg_verbose
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)', nargs="?")
    @arg_flag("-d", "--diff", dest="show_diff", help="show config diffs")
    def handle_audit(self, arg):
        """audit active node configs"""
        confman = core.ConfigMan(arg.root_dir)
        self.verify_op(confman, arg.nodes, show=False, deploy=False,
                       audit=True, show_diff=arg.show_diff,
                       full_match=arg.full_match)

    @argh.alias("verify")
    @arg_full_match
    @argh.arg('nodes', type=str, help='target nodes (regexp)', nargs="?")
    def handle_verify(self, arg):
        """verify local node configs"""
        confman = core.ConfigMan(arg.root_dir)
        manager = self.verify_op(confman, arg.nodes, show=False,
                                 full_match=arg.full_match)

        if manager.error_count:
            self.log.error("failed: files with errors: [%d/%d]",
                           manager.error_count, len(manager.files))
            return 1
        elif not manager.files:
            self.log.info("no files to verify")
        else:
            self.log.info("all [%d] files ok", len(manager.files))

    @argh.alias("add-node")
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
    def handle_add_node(self, arg):
        """add a new node"""
        confman = core.ConfigMan(arg.root_dir)
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
            node_spec = confman.create_node(
                node_name, host=host, parent_node_name=parent_node_name,
                copy_props=arg.copy_props)

            if parent_node_name:
                msg = " <= %s" % (parent_node_name)
            else:
                msg = ""

            logger("node added: %s%s", node_name, msg)

    def color_path(self, output, item, name, is_config=False, is_node=False):
        parts = name.rsplit("/", 1)
        if len(parts) == 1:
            sys_path = None
        else:
            sys_path, name = parts

        if is_config:
            name = output.color(name, "yellow")
            sys_parts = sys_path.split("/", 1)
            if len(sys_parts) == 2:
                sys_path = "%s/%s" % (output.color(sys_parts[0], "cyan"),
                                      output.color(sys_parts[1], "green"))
            else:
                sys_path = output.color(sys_path, "green")
        elif is_node or isinstance(item, core.Node):
            name = output.color(name, "green")
            sys_path = output.color(sys_path, "cyan")
        else:
            name = output.color(name, "cyan")
            sys_path = output.color(sys_path, "cyan")

        if len(parts) == 2:
            name = "%s/%s" % (sys_path, name)

        return name

    @argh.alias("list")
    @arg_full_match
    @argh.arg('pattern', type=str, help='search pattern', nargs="?")
    @arg_flag("-s", "--systems", dest="show_systems", help="show systems")
    @arg_flag("-c", "--config", dest="show_config", help="show node configs")
    @arg_flag("-n", "--config-prop", dest="show_config_prop",
              help="show node config properties")
    @arg_flag("-C", "--controls", dest="show_controls",
              help="show node config control commands")
    @arg_flag("-t", "--tree", dest="show_tree", help="show node tree")
    @arg_flag("-p", "--node-prop", dest="show_node_prop",
              help="show node properties")
    @arg_flag("-o", "--cloud", dest="show_cloud_prop",
              help="show node cloud properties")
    @arg_flag("-q", "--query-status", help="query and show cloud node status")
    @arg_flag("-i", "--inherits", dest="show_inherits",
              help="show node and config inheritances")
    def handle_list(self, arg):
        """list systems and nodes"""
        confman = core.ConfigMan(arg.root_dir)
        output = colors.Output(sys.stdout)
        format_str = "%8s %s"
        HINDENT = 4 * " "
        if arg.show_tree:
            INDENT = HINDENT
        else:
            INDENT = ""

        def norm_name(depth, name):
            if arg.show_tree:
                name = name.rsplit("/", 2)[-1]

            return (INDENT * (depth-1)) + name

        for item in confman.find(arg.pattern, systems=arg.show_systems,
                                 full_match=arg.full_match):
            name = norm_name(item["depth"], item.name)
            name = self.color_path(output, item, name)

            if arg.show_inherits and item.get("parent"):
                name = "%s <= %s" % (name, self.color_path(output, None,
                                                           item.get("parent"),
                                                           is_node=True))

            output.sendline(format_str % (item.type, name))
            if arg.show_node_prop:
                props = output.color_items(item.showable())
                output.sendline(format_str % (
                        "prop", "%s%s%s" % (HINDENT, INDENT*(item["depth"]-1),
                                            props)))

            if arg.show_config and isinstance(item, core.Node):
                for conf in item.iter_configs():
                    item_name = self.color_path(output, item, item.name)
                    config_name = "%s/%s" % (item_name,
                                             output.color(conf.name, "yellow"))
                    name = norm_name(item["depth"] + 1, config_name)
                    if arg.show_inherits and conf.get("parent"):
                        name = "%s <= %s" % (
                            name, self.color_path(output, None,
                                                  conf.get("parent"),
                                                  is_config=True))

                    output.sendline(format_str % ("config", name))

                    doc, controls = conf.get_controls()
                    if arg.show_controls and controls:
                        output.sendline(format_str % ("controls", "%s%s%s" % (
                                HINDENT, INDENT*(item["depth"]),
                                ", ".join(controls))))

                    if arg.show_config_prop:
                        output.sendline(format_str % ("confprop", "%s%s%s" % (
                                    HINDENT, INDENT * (item["depth"]),
                                    output.color_items(conf.iteritems()))))


            cloud_prop = item.get("cloud", {})
            if arg.query_status and cloud_prop.get("instance"):
                provider = self.sky.get_provider(cloud_prop)
                status = provider.get_instance_status(cloud_prop)
                output.sendline(format_str % ("status", "%s%s%s" % (
                            HINDENT, INDENT * (item["depth"] - 1), status)))

            if arg.show_cloud_prop and cloud_prop:
                status = output.color_items(cloud_prop.iteritems(), "cloudkey")
                output.sendline(format_str % (
                        "cloud", "%s%s%s" % (HINDENT,
                                             INDENT * (item["depth"] - 1),
                                             status)))

    def create_parser(self):
        default_root = self.default_repo_path
        if not default_root:
            default_root = os.environ.get("%s_ROOT" % TOOL_NAME.upper())

        if not default_root:
            default_root = (path(os.environ["HOME"]) / (".%s" % TOOL_NAME)
                            / "default")

        parser = argh.ArghParser()
        parser.add_argument("-D", "--debug", dest="debug", default=False,
                            action="store_true", help="enable debug output")
        parser.add_argument(
            "-d", "--root-dir", dest="root_dir", default=default_root,
            metavar="DIR",
            help="repository root directory (default: $HOME/.poni/default)")

        parser.add_commands([
            self.handle_list, self.handle_add_system, self.handle_init,
            self.handle_import, self.handle_script, self.handle_add_config,
            self.handle_update_config,
            self.handle_set, self.handle_show, self.handle_deploy,
            self.handle_audit, self.handle_verify, self.handle_add_node,
            ])

        parser.add_commands([
                self.handle_cloud_init, self.handle_cloud_terminate,
                self.handle_cloud_update, self.handle_cloud_wait,
                ],
                            namespace="cloud", title="cloud operations",
                            help="command to execute")

        parser.add_commands([
                self.handle_remote_exec, self.handle_remote_shell,
                ],
                            namespace="remote", title="remote operations",
                            help="command to execute")

        parser.add_commands([
                self.handle_vc_init, self.handle_vc_diff,
                self.handle_vc_checkpoint,
                ],
                            namespace="vc", title="version-control operations",
                            help="command to execute")

        return parser

    def run(self, args=None):
        def adjust_logging(arg):
            """tune the logging before executing commands"""
            if arg.debug:
                logging.getLogger().setLevel(logging.DEBUG)
            else:
                # paramiko is very talkative at INFO level...
                paramiko_logger = logging.getLogger('paramiko.transport')
                paramiko_logger.setLevel(logging.WARNING)

                # boto blabbers http errors at ERROR severity...
                boto_logger = logging.getLogger('boto')
                boto_logger.setLevel(logging.CRITICAL)

        try:
            exit_code = self.parser.dispatch(argv=args, pre_call=adjust_logging)
        except errors.Error, error:
            self.log.error("%s: %s", error.__class__.__name__, error)
            return -1

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
