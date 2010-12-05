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
        self.indent = int(arg.show_tree) * self.hindent
        self.formatters = {
            "node": self.format_node,
            "system": self.format_system,
            "config": self.format_config,
            "prop": self.format_prop,
            "cloud": self.format_prop,
            "confprop": self.format_prop,
            "status": self.format_status,
            }

    def value_repr(self, value, top_level=False):
        if isinstance(value, unicode):
            try:
                value = repr(value.encode("ascii"))
            except UnicodeEncodeError:
                pass

        if isinstance(value, dict):
            if not value:
                yield "none", "gray"
                raise StopIteration()

            if not top_level:
                yield "{", None

            for i, (key, value) in enumerate(value.iteritems()):
                if i > 0:
                    yield ", ", None

                yield key, "key"
                yield ":", None

                for output in self.value_repr(value):
                    yield output

            if not top_level:
                yield "}", None
        elif isinstance(value, str):
            yield value, "str"
        elif isinstance(value, bool):
            yield str(value), "bool"
        elif isinstance(value, (int, long)):
            yield str(value), "int"
        else:
            yield repr(value), "red"

    def format_status(self, entry):
        yield entry["status"], "status"

    def format_prop(self, entry):
        return self.value_repr(entry["prop"], top_level=True)

    def format_system(self, entry):
        name = entry["item"].name
        if self.arg.show_tree:
            name = name.rsplit("/", 1)[-1]

        yield name, "system"

    def format_node(self, entry):
        system = entry["item"].system
        if not self.arg.show_tree and system.name:
            for output in self.format_system(dict(type="system", item=system)):
                yield output

            yield "/", None

        node_name = entry["item"].name.rsplit("/", 1)[-1]
        yield node_name, "node"

        parent_name = entry["item"].get("parent")
        if parent_name and self.arg.show_inherits:
            yield "(", None
            yield parent_name, "nodeparent"
            yield ")", None

    def format_config(self, entry):
        if not self.arg.show_tree:
            node = False
            for output in self.format_node(entry):
                node = True
                yield output

            if node:
                yield "/", None

        yield entry["config"].name, "config"

        parent_name = entry["config"].get("parent")
        if parent_name and self.arg.show_inherits:
            yield "(", None
            yield parent_name, "configparent"
            yield ")", None

    def format_unknown(self, entry):
        yield "UNKNOWN: %r" % entry["type"], "red"

    def output(self):
        """Yields formatted strings ready for writing to the output file"""
        for text, color_code in self.output_pairs():
            yield self.color(text, color_code)

    def output_pairs(self):
        for entry in self.iter_tree():
            indent = (entry["item"]["depth"] - 1) * self.indent
            if entry["type"] not in ["system", "node", "config"]:
                indent += self.hindent

            if entry["type"] == "config":
                indent += self.indent


            yield "%8s" % entry["type"], None
            yield " ", None
            yield indent, None
            for output in self.formatters.get(entry["type"],
                                              self.format_unknown)(entry):
                yield output

            yield "\n", None


    def iter_tree(self):
        """
        Yields every system, node, config, etc. that needs to be produced to
        the output.
        """
        arg = self.arg

        for item in self.confman.find(arg.pattern, systems=arg.show_systems,
                                      full_match=arg.full_match):
            yield dict(type=["system", "node"][isinstance(item, core.Node)],
                       item=item)

            if arg.show_node_prop:
                yield dict(type="prop", item=item, prop=dict(item.showable()))

            if arg.show_config and isinstance(item, core.Node):
                for conf in item.iter_configs():
                    yield dict(type="config", item=item, config=conf)

                    if arg.show_config_prop:
                        yield dict(type="confprop", item=item, config=conf,
                                   prop=conf)

            cloud_prop = item.get("cloud", {})
            if arg.show_cloud_prop and cloud_prop:
                yield dict(type="cloud", cloud=cloud_prop, item=item,
                           prop=cloud_prop)

            if arg.query_status and cloud_prop.get("instance"):
                provider = self.tool.sky.get_provider(cloud_prop)
                status = provider.get_instance_status(cloud_prop)
                yield dict(type="status", item=item, status=status)
