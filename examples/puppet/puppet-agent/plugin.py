import argh
from poni import config

class PlugIn(config.PlugIn):
    @argh.arg("-x", "--extra", help="extra info")
    def install(self, arg):
        self.log.info("%s/%s install: verbose=%r, extra=%r",
                      self.node.name, self.config.name, arg.verbose,
                      arg.extra)
        if arg.extra:
            print "extra info: %r" % arg.extra

        remote = self.node.get_remote(override=arg.method)
        remote.execute("/root/inst-puppet-agent.sh")
        self.log.info("%s/%s install: install: done",
                      self.node.name, self.config.name)

    def puppetrun(self, arg):
        remote = self.node.get_remote(override=arg.method)
        remote.execute("puppetrun --all")

    def add_controls(self):
        self.add_argh_control("install", self.install)
        self.add_argh_control("puppetrun", self.puppetrun)

    def add_actions(self):
        self.add_file("inst-puppet-agent.sh", mode=0500,
                      dest_path="/root/inst-puppet-agent.sh",
                      render=self.render_cheetah)

