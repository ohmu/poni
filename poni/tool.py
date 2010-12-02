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
import argparse
from path import path
from . import config
from . import errors
from . import util
from . import core
from . import cloud
from . import vc

TOOL_NAME = "poni"


class Tool:
    """command-line tool"""
    def __init__(self, default_repo_path=None):
        self.log = logging.getLogger(TOOL_NAME)
        self.confman = None
        self.default_repo_path = default_repo_path
        self.parser = self.create_parser()
        self.sky = cloud.Sky()

    def create_parser(self):
        """Return an argparse parser object"""
        parser = argparse.ArgumentParser(prog=TOOL_NAME)
        parser.add_argument("-D", "--debug", dest="debug", default=False,
                            action="store_true", help="enable debug output")

        default_root = self.default_repo_path
        if not default_root:
            default_root = os.environ.get("%s_ROOT" % TOOL_NAME.upper())

        if not default_root:
            default_root = str(path(os.environ["HOME"]) / (".%s" % TOOL_NAME))

        # generic arguments
        parser.add_argument(
            "-d", "--root-dir", dest="root_dir", default=default_root,
            metavar="DIR",
            help="repository root directory (default: %s)" % default_root)

        # command sub-parser
        subparsers = parser.add_subparsers(dest="command",
                                           help="command to execute")

        # init
        sub = subparsers.add_parser("init", help="init repository")

        # script
        sub = subparsers.add_parser("script", help="run a script")
        sub.add_argument('script', type=str, help='script file', nargs="?")
        sub.add_argument("-v", "--verbose", default=False,
                         action="store_true", help="verbose output")

        # add-system
        sub = subparsers.add_parser("add-system", help="add a sub-system")
        sub.add_argument('system', type=str, help='name of the system')

        # add-node
        sub = subparsers.add_parser("add-node", help="add a new node")
        sub.add_argument('node', type=str, help='name of the node')
        sub.add_argument("-n", "--count", metavar="N..M", type=str,
                         default="1", help="number of nodes ('N' or 'N..M'")
        sub.add_argument("-H", "--host", metavar="HOST",
                         type=str, default="", dest="host",
                         help="host address")
        sub.add_argument("-i", "--inherit-node", metavar="NODE",
                         type=str, default="", dest="inherit_node",
                         help="inherit from node (regexp)")
        sub.add_argument("-c", "--copy-props", default=False,
                         action="store_true",
                         help="copy parent node's properties")
        sub.add_argument("-v", "--verbose", default=False,
                         action="store_true", help="verbose output")

        # list
        sub = subparsers.add_parser("list", help="list systems and nodes")
        sub.add_argument('pattern', type=str, help='search pattern', nargs="?")
        sub.add_argument("-s", "--systems", dest="show_systems", default=False,
                         action="store_true", help="show systems")
        sub.add_argument("-c", "--config", dest="show_config", default=False,
                         action="store_true", help="show node configs")
        sub.add_argument("-n", "--config-prop", dest="show_config_prop",
                         default=False, action="store_true",
                         help="show node config properties")
        sub.add_argument("-C", "--controls", dest="show_controls",
                         default=False, action="store_true",
                         help="show node config control commands")
        sub.add_argument("-t", "--tree", dest="show_tree", default=False,
                         action="store_true", help="show node tree")
        sub.add_argument("-p", "--node-prop", dest="show_node_prop",
                         default=False, action="store_true",
                         help="show node properties")
        sub.add_argument("-o", "--cloud", dest="show_cloud_prop",
                         default=False, action="store_true",
                         help="show node cloud properties")
        sub.add_argument("-q", "--query-status", dest="query_status",
                         default=False, action="store_true",
                         help="query and show cloud node status")
        sub.add_argument("-i", "--inherits", dest="show_inherits",
                         default=False, action="store_true",
                         help="show node and config inheritances")

        # add-config
        sub = subparsers.add_parser("add-config",
                                    help="add a config to node(s)")
        sub.add_argument('nodes', type=str, help='target nodes (regexp)')
        sub.add_argument('config', type=str, help='name of the config')
        sub.add_argument("-i", "--inherit", metavar="CONFIG",
                         type=str, default="", dest="inherit_config",
                         help="inherit from config (regexp)")
        sub.add_argument("-d", "--copy-dir", metavar="DIR",
                         type=str, default="", dest="copy_dir",
                         help="copy config files from DIR")
        sub.add_argument("-v", "--verbose", default=False,
                         action="store_true", help="verbose output")
        sub.add_argument("-c", "--create-node", default=False,
                         action="store_true",
                         help="create node if it does not exist")

        # verify
        sub = subparsers.add_parser("verify", help="verify local node configs")
        sub.add_argument('nodes', type=str, help='target nodes (regexp)',
                         nargs="?")

        # show
        sub = subparsers.add_parser("show", help="show node configs")
        sub.add_argument('nodes', type=str, help='target nodes (regexp)',
                         nargs="?")
        sub.add_argument("-d", "--show-dynamic", dest="show_dynamic",
                         default=False, action="store_true",
                         help="show dynamic configuration")

        sub = subparsers.add_parser("deploy", help="deploy node configs")
        sub.add_argument('nodes', type=str, help='target nodes (regexp)',
                         nargs="?")
        sub.add_argument("-v", "--verbose", default=False,
                         action="store_true", help="verbose output")

        # control
        sub = subparsers.add_parser(
            "control", help="run control command over node configs")
        sub.add_argument('nodes', type=str, help='target nodes (regexp)')
        sub.add_argument('configs', type=str, help='target configs (regexp)')
        sub.add_argument('control', type=str, help='name of command')
        sub.add_argument('arg', type=str, help='command arg', nargs="*")

        # remote
        remote = subparsers.add_parser("remote", help="run remote commands")
        remote_sub = remote.add_subparsers(dest="rcmd",
                                           help="command to execute")

        # remote exec
        r_exec = remote_sub.add_parser("exec", help="run shell command")
        r_exec.add_argument('nodes', type=str, help='target nodes (regexp)')
        r_exec.add_argument("-v", "--verbose", default=False,
                            action="store_true", help="verbose output")
        r_exec.add_argument('cmd', type=str, help='command to execute')

        # remote shell
        r_shell = remote_sub.add_parser("shell", help="interactive shell")
        r_shell.add_argument("-v", "--verbose", default=False,
                             action="store_true", help="verbose output")
        r_shell.add_argument('nodes', type=str, help='target nodes (regexp)')

        # audit
        sub = subparsers.add_parser("audit", help="audit active node configs")
        sub.add_argument('nodes', type=str, help='target nodes (regexp)',
                         nargs="?")
        sub.add_argument("-d", "--diff", dest="show_diff", default=False,
                         action="store_true", help="show config diffs")

        sub = subparsers.add_parser("set", help="set system/node properties")
        sub.add_argument('target', type=str,
                         help='target systems/nodes (regexp)')
        sub.add_argument('property', type=str, nargs="+",
                         help='property and value ("prop=value")')
        sub.add_argument("-v", "--verbose", default=False,
                         action="store_true", help="verbose output")

        # cloud
        cloud_p = subparsers.add_parser("cloud", help="manage cloud nodes")
        cloud_sub = cloud_p.add_subparsers(dest="ccmd",
                                           help="command to execute")

        # cloud init
        sub = cloud_sub.add_parser("init",
                                   help="reserve a cloud image for nodes")
        sub.add_argument('target', type=str,
                         help='target systems/nodes (regexp)')
        sub.add_argument("--reinit", dest="reinit", default=False,
                         action="store_true", help="re-initialize cloud image")
        sub.add_argument("--wait", dest="wait", default=False,
                         action="store_true",
                         help="wait for instance to start")

        # cloud update
        sub = cloud_sub.add_parser("update",
                                   help="update cloud instance properties ")
        sub.add_argument('target', type=str,
                         help='target systems/nodes (regexp)')

        # cloud terminate
        sub = cloud_sub.add_parser("terminate",
                                   help="terminate cloud instances")
        sub.add_argument('target', type=str,
                         help='target systems/nodes (regexp)')

        # vc
        vc_p = subparsers.add_parser("vc", help="version control")
        vc_sub = vc_p.add_subparsers(dest="vcmd",
                                     help="command to execute")

        # vc init
        sub = vc_sub.add_parser("init", help="init version control in repo")

        # vc status
        sub = vc_sub.add_parser("status", help="show working tree status")

        # vc commit
        sub = vc_sub.add_parser("commit", help="commit all changes")
        sub.add_argument('message', type=str,
                         help='commit message')

        return parser

    def handle_add_system(self, arg):
        system_dir = self.confman.create_system(arg.system)
        self.log.debug("created: %s", system_dir)

    def handle_init(self, arg):
        self.confman.init_repo()

    def handle_script(self, arg):
        try:
            if arg.script:
                lines = file(arg.script).readlines()
            else:
                lines = sys.stdin.readlines()
        except (OSError, IOError), error:
            raise errors.Error("%s: %s" % (error.__class__.__name__, error))

        def wrap(arg):
            if " " in arg:
                return repr(arg)
            else:
                return arg

        for line in lines:
            args = shlex.split(line, comments=True)
            if not args:
                continue

            sub_arg = self.parser.parse_args(args)
            if arg.verbose:
                print "$ " + " ".join(wrap(a) for a in args)

            self.run_one(sub_arg)

    def handle_add_config(self, arg):
        if arg.inherit_config:
            configs = list(self.confman.find_config(arg.inherit_config))
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
        nodes = list(self.confman.find(arg.nodes))
        if arg.create_node and (not nodes):
            # node does not exist, create it as requested
            self.confman.create_node(arg.nodes)
            nodes = self.confman.find(arg.nodes)

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

    def handle_remote_exec(self, arg):
        def rexec(arg, node, remote):
            return remote.execute(arg.cmd)

        rexec.doc = "exec: %r" % arg.cmd
        return self.remote_op(arg, rexec)

    def handle_remote_shell(self, arg):
        def rshell(arg, node, remote):
            remote.shell()

        rshell.doc = "shell"
        self.remote_op(arg, rshell)

    def remote_op(self, arg, op):
        ret = 0
        for node in self.confman.find(arg.nodes):
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

    def handle_vc_init(self, arg):
        if self.confman.vc:
            raise errors.UserError(
                "version control already initialized in this repo")

        self.confman.vc = vc.GitVersionControl(self.confman.root_dir,
                                               init=True)

    def require_vc(self):
        if not self.confman.vc:
            raise errors.UserError(
                "version control not initialized in this repo")

    def handle_vc_status(self, arg):
        self.require_vc()
        for out in self.confman.vc.status():
            print out,

    def handle_vc_commit(self, arg):
        self.require_vc()
        self.confman.vc.commit_all(arg.message)

    def handle_cloud_terminate(self, arg):
        count = 0
        for node in self.confman.find(arg.target):
            cloud_prop = node.get("cloud", {})
            if cloud_prop.get("instance"):
                provider = self.sky.get_provider(cloud_prop)
                provider.terminate_instances([cloud_prop])
                self.log.info("terminated: %s", node.name)
                count += 1

        self.log.info("%s instances terminated", count)

    def handle_cloud_update(self, arg):
        nodes = []
        for node in self.confman.find(arg.target):
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

    def handle_cloud_init(self, arg):
        nodes = []

        def printable(dict_obj):
            return ", ".join(("%s=%r" % item) for item in dict_obj.iteritems())

        for node in self.confman.find(arg.target):
            cloud_prop = node.get("cloud", {})
            if not cloud_prop:
                continue

            if cloud_prop and cloud_prop.get("instance"):
                if not arg.reinit:
                    self.log.warning("%s has already been cloud-initialized, "
                                     "use --reinit to override",
                                     node.name)
                    continue
                else:
                    self.log.info("%s: reinit: existing config scrapped: %s",
                                  node.name, cloud_prop)

            provider = self.sky.get_provider(cloud_prop)
            props = provider.init_instance(cloud_prop)
            node.update(props)
            node.save()
            self.log.info("%s: initialized: %s", node.name,
                          printable(props["cloud"]))
            nodes.append(node)

        if arg.wait and nodes:
            props = [n["cloud"] for n in nodes]
            updates = provider.wait_instances(props)

            for node in nodes:
                node_update = updates[node["cloud"]["instance"]]
                node.update(node_update)
                node.save()
                self.log.info("%s update: %s", node.name,
                              printable(node_update))

    def handle_set(self, arg):
        props = dict(util.parse_prop(p) for p in arg.property)
        logger = logging.info if arg.verbose else logging.debug
        for item in self.confman.find(arg.target, systems=True):
            changes = item.set_properties(props)
            for key, old_value, new_value in changes:
                logger("%s: set %s=%r (was %r)", item.name, key, new_value,
                       old_value)

            item.save()

    def collect_all(self, manager):
        items = []
        for item in self.confman.find("."):
            item.collect(manager)
            items.append(item)

        # parents need to be collected _after_ all nodes have been collected,
        # so that every parent node is loaded and available with full props
        for item in items:
            item.collect_parents(manager)

        return items

    def verify_op(self, target, **verify_options):
        manager = config.Manager(self.confman)
        self.collect_all(manager)

        if target:
            re_target = re.compile(target)
            def target_filter(item):
                return re_target.search(item["node"].name)
        else:
            target_filter = lambda item: True

        manager.verify(callback=target_filter, **verify_options)
        return manager

    def handle_show(self, arg):
        manager = self.verify_op(arg.nodes, show=(not arg.show_dynamic))
        if arg.show_dynamic:
            for item in manager.dynamic_conf:
                print item

    def handle_deploy(self, arg):
        self.verify_op(arg.nodes, show=False, deploy=True, verbose=arg.verbose)

    def handle_audit(self, arg):
        self.verify_op(arg.nodes, show=False, deploy=False, audit=True,
                       show_diff=arg.show_diff)

    def handle_verify(self, arg):
        manager = self.verify_op(arg.nodes, show=False)

        if manager.error_count:
            self.log.error("failed: files with errors: [%d/%d]",
                           manager.error_count, len(manager.files))
            return 1
        elif not manager.files:
            self.log.info("no files to verify")
        else:
            self.log.info("all [%d] files ok", len(manager.files))

    def handle_add_node(self, arg):
        if arg.inherit_node:
            nodes = list(self.confman.find(arg.inherit_node))
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
            node_spec = self.confman.create_node(
                node_name, host=host, parent_node_name=parent_node_name,
                copy_props=arg.copy_props)

            if parent_node_name:
                msg = " <= %s" % (parent_node_name)
            else:
                msg = ""

            logger("node added: %s%s", node_name, msg)

    def handle_list(self, arg):
        format_str = "%8s %s"
        if arg.show_tree:
            INDENT = " " * 4
        else:
            INDENT = ""

        def norm_name(depth, name):
            if arg.show_tree:
                name = name.rsplit("/", 2)[-1]

            return (INDENT * (depth-1)) + name

        for item in self.confman.find(arg.pattern, systems=arg.show_systems):
            name = norm_name(item["depth"], item.name)
            if arg.show_inherits and item.get("parent"):
                name = "%s <= %s" % (name, item.get("parent"))

            print format_str % (item.type, name)
            if arg.show_node_prop:
                props = str(item)
                print format_str % ("prop",
                                    "%s%s" % (INDENT*item["depth"], props))

            if arg.show_config and isinstance(item, core.Node):
                for conf in item.iter_configs():
                    config_name = "%s/%s" % (item.name, conf.name)
                    name = norm_name(item["depth"] + 1, config_name)
                    if arg.show_inherits and conf.get("parent"):
                        name = "%s <= %s" % (name, conf.get("parent"))

                    print format_str % ("config", name)

                    doc, controls = conf.get_controls()
                    if arg.show_controls and controls:
                        print format_str % ("controls", "%s%s" % (
                                INDENT*(item["depth"]+1), ", ".join(controls)))

                    if arg.show_config_prop:
                        print format_str % ("confprop", "%s%s" % (
                                INDENT*(item["depth"]+1), conf))


            cloud_prop = item.get("cloud", {})
            if arg.query_status and cloud_prop.get("instance"):
                provider = self.sky.get_provider(cloud_prop)
                status = provider.get_instance_status(cloud_prop)
                print format_str % ("status", "%s%s" % (INDENT*item["depth"],
                                                        status))

            if arg.show_cloud_prop and cloud_prop:
                status = ", ".join(("%s=%r" % i)
                                   for i in cloud_prop.iteritems())
                print format_str % ("cloud", "%s%s" % (INDENT*item["depth"],
                                                       status))

    def run(self, args=None):
        """
        Run a single command given as an 'args' list.

        Returns a non-zero integer on errors.
        """
        arg = self.parser.parse_args(args)
        must_exist = (arg.command not in ["script", "init"])

        try:
            self.confman = core.ConfigMan(path(arg.root_dir),
                                          must_exist=must_exist)
            if arg.debug:
                logging.getLogger().setLevel(logging.DEBUG)
            else:
                # paramiko is very talkative at INFO level...
                paramiko_logger = logging.getLogger('paramiko.transport')
                paramiko_logger.setLevel(logging.WARNING)

                # boto blabbers http errors at ERROR severity...
                boto_logger = logging.getLogger('boto')
                boto_logger.setLevel(logging.CRITICAL)

            return self.run_one(arg)
        except errors.Error, error:
            self.log.error("%s: %s", error.__class__.__name__, error)
            return -1
        finally:
            if self.confman:
                self.confman.cleanup()


    def run_one(self, arg):
        """Run a single command specified in the already parsed 'arg' object"""
        if arg.command == "remote":
            handler_name = "handle_remote_%s" % arg.rcmd.replace("-", "_")
        elif arg.command == "cloud":
            handler_name = "handle_cloud_%s" % arg.ccmd.replace("-", "_")
        elif arg.command == "vc":
            handler_name = "handle_vc_%s" % arg.vcmd.replace("-", "_")
        else:
            handler_name = "handle_%s" % arg.command.replace("-", "_")

        op = getattr(self, handler_name)
        return op(arg)

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
