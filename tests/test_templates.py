from __future__ import print_function
from pytest import skip
from poni import template
from poni import tool
from helper import *
import os


single_xml_file_plugin_text = """
from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("%(source)s", dest_path="%(dest)s",
                      render=self.render_genshi_xml)
"""

genshi_xml_template = """\
<test xmlns:py="http://genshi.edgewall.org/">
  <foo py:content="node.host"/>
</test>
"""

class objectvar(object):
    val1 = "object variable 1"
    val2 = {"key": "dict in object variable 2"}

g_vars = {
    "text": "dummy text variable",
    "object": objectvar,
    "dict": {"key": "dummy value in a dict"},
    }

class TestTemplates(Helper):
    def test_xml_template(self):
        if not template.genshi:
            skip("Genshi not available")

        poni, repo = self.init_repo()

        # add template config
        template_node = "tnode"
        template_conf = "tconf"
        assert not poni.run(["add-node", template_node])
        assert not poni.run(["set", template_node, "verify:bool=off"])
        assert not poni.run(["add-config", template_node, template_conf])

        # write template config plugin.py
        tconf_path = "%s/%s" % (template_node, template_conf)
        conf_dir = os.path.join(repo, "system", template_node, "config", template_conf)
        tplugin_path = os.path.join(conf_dir, "plugin.py")
        output_file = self.temp_file()
        tfile = self.temp_file()
        with open(tfile, "w") as f:
            f.write(genshi_xml_template)
        args = dict(source=tfile, dest=output_file)
        with open(tplugin_path, "w") as f:
            f.write(single_xml_file_plugin_text % args)

        # add inherited config
        instance_node = "inode"
        instance_conf = "iconf"
        assert not poni.run(["add-node", instance_node])
        assert not poni.run(["set", instance_node, "deploy=local", "host=baz"])
        assert not poni.run(["add-config", instance_node, instance_conf,
                             "--inherit", tconf_path])

        # deploy and verify
        assert not poni.run(["deploy"])
        with open(output_file, "r") as f:
            output = f.read()
        print(output)
        assert "<foo>baz</foo>" in output

    name_tests = {
        "foo": "foo",
        "foo [$text]": "foo [dummy text variable]",
        "foo ${dict.key}bar": "foo dummy value in a dictbar",
        "foo \\${dict.key}bar": "foo ${dict.key}bar",
        "foo \\$1": "foo $1",
        "foo \\\\$object.val1": "foo \\$object.val1",
        "foo \\$object.val1": "foo $object.val1",
        "foo $object.val1": "foo object variable 1",
        "$object.val2.key: x": "dict in object variable 2: x",
        }

    def test_render_name(self):
        for tmpl, exp in self.name_tests.items():
            res = template.render_name(tmpl, None, g_vars)
            assert exp == res, \
                "template {0!r}, expected {1!r}, got {2!r}".format(tmpl, exp, res)

    def test_render_cheetah(self):
        if not template.CheetahTemplate:
            skip("CheetahTemplate not available")
        for tmpl, exp in self.name_tests.items():
            res = template.render_cheetah(tmpl, None, g_vars)
            assert exp == res, \
                "template {0!r}, expected {1!r}, got {2!r}".format(tmpl, exp, res)
