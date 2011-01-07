"""
Node remote control switchboard

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

from . import rcontrol
from . import rcontrol_paramiko
#from . import rcontrol_openssh
from . import errors

METHODS = {
    "ssh": rcontrol_paramiko.ParamikoRemoteControl,
    "local": rcontrol.LocalControl,
    }

class RemoteManager:
    def __init__(self):
        self.remotes = {}

    def cleanup(self):
        for remote in self.remotes.values():
            remote.close()

    def get_remote(self, node, method):
        key = (node.name, method)
        remote = self.remotes.get(key)
        if not remote:
            try:
                control_class = METHODS[method or "ssh"]
            except KeyError:
                raise errors.RemoteError(
                    "unknown remote control method %r" % method)

            remote = control_class(node)
            self.remotes[key] = remote

        return remote

manager = RemoteManager()

get_remote = manager.get_remote

