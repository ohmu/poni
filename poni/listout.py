"""
List output formatting

TODO: messy, rewrite

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

import sys
from . import colors
from . import core


class ListOutput(colors.Output):
    def __init__(self, tool, confman, arg):
        colors.Output.__init__(self, sys.stdout)
        self.tool = tool
        self.confman = confman
        self.arg = arg
        self.hindent = 4 * " "
        self.indent = int(not arg.show_tree) * self.hindent

    def color_path(self, item, name, is_config=False, is_node=False):
        parts = name.rsplit("/", 1)
        if len(parts) == 1:
            sys_path = None
        else:
            sys_path, name = parts

        if is_config:
            name = self.color(name, "yellow")
            sys_parts = sys_path.split("/", 1)
            if len(sys_parts) == 2:
                sys_path = "%s/%s" % (self.color(sys_parts[0], "cyan"),
                                      self.color(sys_parts[1], "green"))
            else:
                sys_path = self.color(sys_path, "green")
        elif is_node or isinstance(item, core.Node):
            name = self.color(name, "green")
            sys_path = self.color(sys_path, "cyan")
        else:
            name = self.color(name, "cyan")
            sys_path = self.color(sys_path, "cyan")

        if len(parts) == 2:
            name = "%s/%s" % (sys_path, name)

        return name

    def output(self):
        format_str = "%8s %s"

        def norm_name(depth, name):
            if arg.show_tree:
                name = name.rsplit("/", 2)[-1]

            return (self.indent * (depth-1)) + name

        arg = self.arg

        for item in self.confman.find(arg.pattern, systems=arg.show_systems,
                                      full_match=arg.full_match):
            name = norm_name(item["depth"], item.name)
            name = self.color_path(item, name)

            if arg.show_inherits and item.get("parent"):
                name = "%s <= %s" % (name, self.color_path(None,
                                                           item.get("parent"),
                                                           is_node=True))

            yield format_str % (item.type, name)
            if arg.show_node_prop:
                props = self.color_items(item.showable())
                yield format_str % (
                    "prop", "%s%s%s" % (self.hindent,
                                        self.indent*(item["depth"]-1),
                                        props))

            if arg.show_config and isinstance(item, core.Node):
                for conf in item.iter_configs():
                    item_name = self.color_path(item, item.name)
                    config_name = "%s/%s" % (item_name,
                                             self.color(conf.name, "yellow"))
                    name = norm_name(item["depth"] + 1, config_name)
                    if arg.show_inherits and conf.get("parent"):
                        name = "%s <= %s" % (
                            name, self.color_path(None,
                                                  conf.get("parent"),
                                                  is_config=True))

                    yield format_str % ("config", name)

                    doc, controls = conf.get_controls()
                    if arg.show_controls and controls:
                        yield format_str % ("controls", "%s%s%s" % (
                            self.hindent, self.indent*(item["depth"]),
                            ", ".join(controls)))

                    if arg.show_config_prop:
                        yield format_str % (
                            "confprop", "%s%s%s" % (
                                self.hindent, self.indent * (item["depth"]),
                                self.color_items(conf.iteritems())))


            cloud_prop = item.get("cloud", {})
            if arg.query_status and cloud_prop.get("instance"):
                provider = self.tool.sky.get_provider(cloud_prop)
                status = provider.get_instance_status(cloud_prop)
                yield format_str % ("status", "%s%s%s" % (
                    self.hindent, self.indent * (item["depth"] - 1),
                    status))

            if arg.show_cloud_prop and cloud_prop:
                status = self.color_items(cloud_prop.iteritems(), "cloudkey")
                yield format_str % (
                    "cloud", "%s%s%s" % (self.hindent,
                                         self.indent * (item["depth"] - 1),
                                         status))

