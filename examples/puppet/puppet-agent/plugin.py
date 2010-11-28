from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("inst-puppet-agent.sh", mode=0500,
                      dest_path="/root/inst-puppet-agent.sh",
                      render=self.render_cheetah)

