import json
from poni import tool
from helper import *

single_file_plugin_text = """
from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("%(source)s", dest_path="%(dest)s", auto_override=%(override)s)
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

    def _make_inherited_config(self, template_node, template_conf,
                               instance_node, instance_conf,
                               source_file, file_contents, output_file,
                               auto_override=False):
        # add template config
        tconf_path = "%s/%s" % (template_node, template_conf)
        source_file = "test.txt"
        args = dict(source=source_file, dest=output_file, override=auto_override)
        plugin_text = single_file_plugin_text % args

        poni = self.repo_and_config(template_node, template_conf, plugin_text)
        assert not poni.run(["set", template_node, "verify:bool=off"])

        # write template config template file
        tfile_path = poni.default_repo_path / "system" / template_node / "config" / template_conf / source_file
        tfile_path.open("w").write(file_contents)

        # add inherited config
        assert not poni.run(["add-node", instance_node])
        assert not poni.run(["set", instance_node, "deploy=local"])
        assert not poni.run(["add-config", instance_node, instance_conf,
                             "--inherit", tconf_path])
        # deploy and verify
        assert not poni.run(["deploy"])
        return poni

    def test_config_inherit(self):
        template_text = "hello"
        output_file = self.temp_file()
        poni = self._make_inherited_config("tnode", "tconf", "inode", "iconf",
                                           "test.txt", template_text, output_file)
        assert output_file.bytes() == template_text

    def test_auto_override_config(self):
        template_text = "hello"
        output_file = self.temp_file()
        poni = self._make_inherited_config("tnode", "tconf", "inode", "iconf",
                                           "test.txt", template_text, output_file,
                                           auto_override=True)
        assert output_file.bytes() == template_text
        # update inherited node with new content in "test.txt"
        new_template_text = "world"
        tmpfile = self.temp_dir() / "test.txt"
        tmpfile.write_bytes(new_template_text)
        poni.run(["update-config", "-v", "inode/iconf", tmpfile])
        # see if the file is deployed with changed content
        poni.run(["deploy"])
        assert output_file.bytes() == new_template_text

    def test_require(self):
        poni, repo = self.init_repo()
        assert not poni.run(["require", "poni_version>='0.1'"])
        assert not poni.run(["require", "-v", "poni_version<'100'"])
        assert poni.run(["require", "poni_version=='0.0'"]) == -1
        assert poni.run(["require", "xxx"]) == -1

    def test_version(self):
        poni, repo = self.init_repo()
        assert not poni.run(["version"])
