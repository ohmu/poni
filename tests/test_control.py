import json
from poni import tool
from helper import *

plugin_text = """
import argh
from poni import config

class PlugIn(config.PlugIn):
    @config.control(provides=["foo"])
    @argh.arg("output")
    def foo(self, arg):
        file(arg.output, "a").write("foo")

    @config.control(requires=["foo"])
    @argh.arg("output")
    def bar(self, arg):
        file(arg.output, "a").write("bar")

    @config.control(optional_requires=["foo"])
    @argh.arg("output")
    def baz(self, arg):
        file(arg.output, "a").write("baz")

    @config.control(optional_requires=["xxx"])
    @argh.arg("output")
    def bax(self, arg):
        file(arg.output, "a").write("bax")

"""

class TestControls(Helper):
    def test_basic_controls(self):
        poni, repo = self.init_repo()
        node = "node"
        conf = "conf"
        assert not poni.run(["add-node", node])
        assert not poni.run(["add-config", node, conf])
        conf_path = "%s/%s" % (node, conf)
        output_dir = path(self.temp_file())
        output_dir.makedirs()
        plugin_py = output_dir / "plugin.py"
        plugin_py.write_bytes(plugin_text)
        assert not poni.run(["update-config", conf_path, plugin_py])

        temp = self.temp_file()

        assert not poni.run(["control", ".", "foo", "--", temp])
        assert file(temp).read() == "foo"
        os.unlink(temp)

        assert not poni.run(["control", ".", "bar", "--", temp])
        assert file(temp).read() == "foobar"
        os.unlink(temp)

        assert not poni.run(["control", ".", "baz", "--", temp])
        assert file(temp).read() == "foobaz"
        os.unlink(temp)

        assert not poni.run(["control", ".", "bax", "--", temp])
        assert file(temp).read() == "bax"
        os.unlink(temp)
