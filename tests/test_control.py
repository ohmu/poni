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
        open(arg.output, "a").write("foo")

    @config.control(requires=["foo"])
    @argh.arg("output")
    def bar(self, arg):
        open(arg.output, "a").write("bar")

    @config.control(optional_requires=["foo"])
    @argh.arg("output")
    def baz(self, arg):
        open(arg.output, "a").write("baz")

    @config.control(optional_requires=["xxx"])
    @argh.arg("output")
    def bax(self, arg):
        open(arg.output, "a").write("bax")

"""

class TestControls(Helper):
    def test_basic_controls(self):
        poni = self.repo_and_config("node", "conf", plugin_text)
        temp = self.temp_file()

        def cmd_output(cmd, output):
            assert not poni.run(["control", ".", cmd, "--", temp])
            assert open(temp).read() == output
            os.unlink(temp)

        cmd_output("foo", "foo")
        cmd_output("bar", "foobar")
        cmd_output("baz", "foobaz")
        cmd_output("bax", "bax")
