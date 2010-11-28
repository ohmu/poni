import os
from poni import config
import subprocess

def dot(file_path):
    subprocess.call(["dot", "-Tpng", "-o", 
                     "%s.png" % os.path.splitext(file_path)[0],
                     file_path])


class PlugIn(config.PlugIn):
    def add_actions(self):
        self.add_file("report.txt", dest_path="/tmp/report.txt",
                      render=self.render_cheetah, report=True)
        self.add_file("network.dot", dest_path="/tmp/network.dot",
                      render=self.render_cheetah, report=True,
                      post_process=dot)

