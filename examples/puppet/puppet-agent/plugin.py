import argh
from poni import config
from poni import errors

INST_AGENT_SH = "/root/inst-puppet-agent.sh"

class PlugIn(config.PlugIn):
    @argh.arg("-x", "--extra", help="extra info")
    def install(self, arg):
        self.log.info("%s/%s install: verbose=%r, extra=%r",
                      self.node.name, self.config.name, arg.verbose,
                      arg.extra)
        if arg.extra:
            print "extra info: %r" % arg.extra

        remote = self.node.get_remote(override=arg.method)
        exit_code = remote.execute(INST_AGENT_SH, verbose=arg.verbose)
        if exit_code:
            raise errors.ControlError("%r failed with exit code %r" % (
                    INST_AGENT_SH, exit_code))

        self.log.info("%s/%s install - done",
                      self.node.name, self.config.name)

    def puppetrun(self, arg):
        remote = self.node.get_remote(override=arg.method)
        remote.execute("puppetrun --all")

    def add_controls(self):
        self.add_argh_control(self.install, requires=["puppet-master"])
        self.add_argh_control(self.puppetrun)

    def add_actions(self):
        self.add_file("inst-puppet-agent.sh", mode=0500,
                      dest_path=INST_AGENT_SH, render=self.render_cheetah)

