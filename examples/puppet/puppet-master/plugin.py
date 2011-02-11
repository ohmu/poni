import argh
from poni import config
from poni import errors

INST_MASTER_SH = "/root/inst-puppet-master.sh"

class PlugIn(config.PlugIn):
    @argh.arg("-x", "--extra", help="extra info")
    def install(self, arg):
        self.log.info("%s/%s install: verbose=%r, extra=%r",
                      self.node.name, self.config.name, arg.verbose,
                      arg.extra)
        if arg.extra:
            print "extra info: %r" % arg.extra

        remote = self.node.get_remote(override=arg.method)
        exit_code = remote.execute(INST_MASTER_SH, verbose=arg.verbose)
        if exit_code:
            raise errors.ControlError("%r failed with exit code %r" % (
                    INST_MASTER_SH, exit_code))

        self.log.info("%s/%s install - done",
                      self.node.name, self.config.name)

    def add_controls(self):
        self.add_argh_control(self.install, provides=["puppet-master"])

    def add_actions(self):
        self.add_file("site.pp", dest_path="/etc/puppet/manifests/",
                      report=True)
        self.add_file("inst-puppet-master.sh", mode=0500,
                      dest_path=INST_MASTER_SH)
