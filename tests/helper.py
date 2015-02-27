import json
import itertools
import shutil
import os
import tempfile
import unittest
from poni import tool


class Helper(unittest.TestCase):
    def __init__(self, *args, **kwa):
        super(Helper, self).__init__(*args, **kwa)
        self.temp_files = []

    def temp_file(self, prefix="test_poni"):
        f = tempfile.mktemp(prefix=prefix)
        self.temp_files.append(f)
        return f

    def temp_dir(self, prefix="test_poni_dir"):
        d = tempfile.mkdtemp(prefix=prefix)
        self.temp_files.append(d)
        return d

    def setup(self):
        pass

    def teardown(self):
        for temp_file in self.temp_files:
            if os.path.isfile(temp_file):
                os.unlink(temp_file)
            elif os.path.isdir(temp_file):
                shutil.rmtree(temp_file)

    def init_repo(self):
        repo = self.temp_file()
        poni = tool.Tool(default_repo_path=repo)
        assert not poni.run(["init"])
        config = json.load(open(os.path.join(repo, "repo.json")))
        assert isinstance(config, dict)
        return poni, repo

    def repo_and_config(self, node, conf, plugin_text, copy=None):
        poni, repo = self.init_repo()
        assert not poni.run(["add-node", node])
        add_conf = ["add-config", node, conf]
        if copy:
            add_conf.extend(["-d", copy])

        assert not poni.run(add_conf)
        conf_path = os.path.join(node, conf)
        output_dir = self.temp_file()
        os.makedirs(output_dir)
        plugin_py = os.path.join(output_dir, "plugin.py")
        open(plugin_py, "w").write(plugin_text)
        assert not poni.run(["update-config", conf_path, plugin_py])
        return poni


def combos(seq, max_len=None):
    seq = list(seq)
    for length in range(0, max_len or (len(seq) + 1)):
        for combo in itertools.combinations(seq, length):
            yield combo
