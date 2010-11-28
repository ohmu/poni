from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("tables.sql", dest_path="/tmp/tables${node.index}.sql", 
                      render=self.render_cheetah)
        self.add_file("tables2.sql", dest_path="/tmp/blah${node.index}.sql", 
                      render=self.render_cheetah)

