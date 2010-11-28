from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("deb6-upgrade.sh", mode=0500,
                      dest_path="/root/deb6-upgrade.sh",
                      render=self.render_cheetah)

