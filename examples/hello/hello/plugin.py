from poni import config

class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("hello.txt", mode=0644, dest_path="/tmp/")

    @config.control()
    def loadavg(self, arg):
        print "foo!"
