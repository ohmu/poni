from __future__ import print_function
import random
import json
from poni import tool
from helper import *
from poni import times

def test_times():
    tasks = times.Times()
    N = 10
    for i in range(0, N):
        start = random.uniform(1000, 2000)
        stop = start + random.uniform(1, 1000)
        tasks.add_task(i, "task%d" % i, start, stop)

    report = "".join(tasks.iter_report())
    print(report)
    for i in range(0, N):
        name = "task%d" % i
        assert name in report, "%r missing from report" % name



plugin_text = """
from poni import config
import time

class PlugIn(config.PlugIn):
    @config.control()
    def dummy(self, arg):
        print("dummy")

"""

class TestClockedOps(Helper):
    def setup_method(self, method):
        Helper.setup(self)
        self.poni = self.repo_and_config("node", "conf", plugin_text)
        self.time_log = self.temp_file()
        self.verify = []

    def op(self, args, verify=None):
        full_args = ["-L", self.time_log] + args
        assert not self.poni.run(full_args)
        if verify:
            self.verify.append(verify)
            self.verify_log(self.verify)

    def test_simple(self):
        self.op(["-T", "one", "version"],
                verify=dict(name="one", task_id="C"))
        self.op(["-T", "-", "version"],
                verify=dict(name="-L %s -T - version" % self.time_log, task_id="C"))
        self.op(["-T", "two", "version"],
                verify=dict(name="two", task_id="C"))
        self.op(["control", "-t", "node/conf", "dummy"],
                verify=dict(task_id=0, name="node/conf"))
        self.op(["report"])
        # TODO: verify output

    def verify_log(self, ops):
        with open(self.time_log, "r") as f:
            data = json.load(f)
        def has_all(a, b):
            assert a["stop"] >= a["start"]
            for k, v in b.items():
                if a.get(k) != v:
                    return False

            return True

        for op in ops:
            assert any(has_all(d, op) for d in data)
