from poni import tool
from helper import *

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

class TestTemplates(Helper):
    def test_xml_template(self):
        poni, repo = self.init_repo()

        # add template config
        template_node = "tnode"
        template_conf = "tconf"
        assert not poni.run(["add-node", template_node])
        assert not poni.run(["set", template_node, "verify:bool=off"])
        assert not poni.run(["add-config", template_node, template_conf])

        # write template config plugin.py
        tconf_path = "%s/%s" % (template_node, template_conf)
        conf_dir = repo / "system" / template_node / "config" / template_conf
        tplugin_path = conf_dir / "plugin.py"
        output_file = self.temp_file()
        tfile = self.temp_file()
        file(tfile, "w").write(genshi_xml_template)
        args = dict(source=tfile, dest=output_file)
        tplugin_path.open("w").write(single_xml_file_plugin_text % args)

        # add inherited config
        instance_node = "inode"
        instance_conf = "iconf"
        assert not poni.run(["add-node", instance_node])
        assert not poni.run(["set", instance_node, "deploy=local", "host=baz"])
        assert not poni.run(["add-config", instance_node, instance_conf,
                             "--inherit", tconf_path])

        # deploy and verify
        assert not poni.run(["deploy"])
        output = output_file.bytes()
        print output
        assert "<foo>baz</foo>" in output
