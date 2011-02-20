import json
from poni import tool
from helper import *

plugin_text = """
from poni import config

class PlugIn(config.PlugIn):
    pass

"""

class TestSettings(Helper):
    def test_settings_list_empty(self):
        poni = self.repo_and_config("node", "conf", plugin_text)
        assert not poni.run(["settings", "list"])

    def test_settings_set(self):
        input_dir = self.temp_file()
        settings_dir = input_dir / "settings"
        settings_dir.makedirs()
        defaults_file = settings_dir / "00-defaults.json"
        defaults = {"foo":"bar"}
        defaults_file.write_bytes(json.dumps(defaults))

        poni = self.repo_and_config("node", "conf", plugin_text, 
                                    copy=input_dir)
        
        assert not poni.run(["settings", "list"])
        # TODO: verify output

        assert not poni.run(["settings", "set", "node/conf", "foo=baz"])
        assert not poni.run(["settings", "list"])
        # TODO: verify list output

    # TODO: test for invalid 'set' value types
    # TODO: test for inherited scenarios
