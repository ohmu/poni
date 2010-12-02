from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("site.pp", dest_path="/etc/puppet/manifests/",
                      report=True)
        self.add_file("inst-puppet-master.sh", mode=0500,
                      dest_path="/root/")
