import json
from poni import tool
from helper import *

single_file_plugin_text = """
from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("%(source)s", dest_path="%(dest)s")
"""

class TestCommands(Helper):
    def test_add_node(self):
        poni, repo = self.init_repo()
        nodes = ["foo", "bar/foo/baz"]
        for node in nodes:
            poni.run(["add-node", node])
            node_config = repo / "system" / node / "node.json"
            config = json.load(file(node_config))
            print node, config
            assert isinstance(config, dict)
            assert config["host"] == ""

    def test_create(self):
        poni, repo = self.init_repo()
        nodes = ["foo", "bar/foo/baz"]
        for node in nodes:
            poni.run(["add-system", node])
            node_config = repo / "system" / node / "system.json"
            config = json.load(file(node_config))
            print node, config
            assert isinstance(config, dict)
            assert config == {}

    def test_set(self):
        poni, repo = self.init_repo()
        node = "test"
        assert not poni.run(["add-node", node])
        vals = {
            "foo": ("=bar", "bar"),
            "a": ("=b=c", "b=c"),
            "int": (":int=1", 1),
            "float": (":float=2", 2.0),
            "str": (":str=123", "123"),
            "b0": (":bool=0", False),
            "b1": (":bool=1", True),
            "bt": (":bool=true", True),
            "bf": (":bool=false", False),
            "bon": (":bool=on", True),
            "boff": (":bool=off", False),
            }

        node_config = repo / "system" / node / "node.json"
        for key, val in vals.iteritems():
            if isinstance(val, (str, unicode)):
                inval = val
                outval = val
            else:
                inval, outval = val

            set_str = "%s%s" % (key, inval)
            assert not poni.run(["set", node, set_str])

            config = json.load(file(node_config))
            assert config[key] == outval, "got %r, expected %r" % (
                config[key], outval)

        assert not poni.run(["set", node, "one.two.three.four=five", "-v"])
        config = json.load(file(node_config))
        assert config["one"]["two"]["three"]["four"] == "five"

    def test_list(self):
        poni, repo = self.init_repo()
        node = "test"
        conf = "conf"
        assert not poni.run(["add-node", node])
        assert not poni.run(["add-config", node, conf])
        assert not poni.run(["set", node, "cloud.blah=foo"])
        flags = ["--systems", "--config", "--tree", "--full-match",
                 "--controls", "--nodes", "--systems",
                 "--node-prop", "--cloud", "--query-status", "--config-prop",
                 "--inherits", "--line-per-prop"]
        for combo in combos(flags, max_len=4):
            cmd = ["list"]
            cmd.extend(combo)
            print cmd
            assert not poni.run(cmd)

    def test_script(self):
        for combo in combos(["--verbose"]):
            poni, repo = self.init_repo()
            node = "test"
            script_file = self.temp_file()
            file(script_file, "w").write(
                "add-node %s\nset %s foo=bar" % (node, node))
            assert not poni.run(["script", script_file])
            node_config = repo / "system" / node / "node.json"
            config = json.load(file(node_config))
            assert config["foo"] == "bar"

        # TODO: stdin version of "script" command

    def test_verify_no_content(self):
        poni, repo = self.init_repo()
        node = "test"
        conf = "conf"
        assert not poni.run(["add-node", node])
        assert not poni.run(["add-config", node, conf])
        assert not poni.run(["verify"])
        assert not poni.run(["deploy"])
        assert not poni.run(["audit"])

    def test_config_inherit(self):
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
        tfile = "test.txt"
        args = dict(source=tfile, dest=output_file)
        tplugin_path.open("w").write(single_file_plugin_text % args)

        # write template config template file
        tfile_path = conf_dir / tfile
        template_text = "hello"
        tfile_path.open("w").write(template_text)

        # add inherited config
        instance_node = "inode"
        instance_conf = "iconf"
        assert not poni.run(["add-node", instance_node])
        assert not poni.run(["set", instance_node, "deploy=local"])
        assert not poni.run(["add-config", instance_node, instance_conf,
                             "--inherit", tconf_path])

        # deploy and verify
        assert not poni.run(["deploy"])
        output = output_file.bytes()
        assert output == template_text

    def test_require(self):
        poni, repo = self.init_repo()
        assert not poni.run(["require", "poni_version>='0.1'"])
        assert not poni.run(["require", "-v", "poni_version<'100'"])
        assert poni.run(["require", "poni_version=='0.0'"]) == -1
        assert poni.run(["require", "xxx"]) == -1

    def test_version(self):
        poni, repo = self.init_repo()
        assert not poni.run(["version"])
