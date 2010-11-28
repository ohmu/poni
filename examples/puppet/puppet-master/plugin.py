from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("site.pp",
                      dest_path="/etc/puppet/manifests/site.pp",
                      report=True,
                      render=self.render_cheetah)
        self.add_file("inst-puppet-master.sh", mode=0500,
                      dest_path="/root/inst-puppet-master.sh",
                      render=self.render_cheetah)
