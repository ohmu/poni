from poni import tool
from helper import *
import subprocess

class TestVersionControl(Helper):
    def git(self, repo, cmd):
        full_cmd = ["git",
                    "--git-dir=%s/.git" % repo,
                    "--work-tree=%s" % repo] + cmd
        print "git cmd: %r" % full_cmd
        git = subprocess.Popen(full_cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        git.wait()
        stdout = git.stdout.read()
        stderr = git.stderr.read()
        print "git stdout: %r" % stdout
        print "git stderr: %r" % stderr
        assert git.returncode == 0
        return stdout

    def vc_init(self):
        poni, repo = self.init_repo()

        assert not poni.run(["add-node", "foo/bar"])
        assert not poni.run(["add-config", "foo/bar", "baz"])

        assert not poni.run(["vc", "init"])

        assert (repo / ".git").exists()
        assert self.git(repo, ["status", "-s"]) == ""

        return poni, repo

    def test_checkpoint(self):
        poni, repo = self.vc_init()
        assert not poni.run(["add-node", "foo/bar2"])
        assert not poni.run(["add-config", "foo/bar2", "baz2"])
        assert "foo/bar2" in self.git(repo, ["status", "-s"])
        assert not poni.run(["vc", "checkpoint", "checkpoint changes"])
        assert self.git(repo, ["status", "-s"]) == ""
        assert "checkpoint changes" in self.git(repo, ["log"])

