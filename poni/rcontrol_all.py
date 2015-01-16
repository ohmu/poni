"""
Node remote control switchboard

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

from . import rcontrol
from . import rcontrol_paramiko
#from . import rcontrol_openssh
from . import errors

METHODS = {
    "ssh": rcontrol_paramiko.ParamikoRemoteControl,
    "local": rcontrol.LocalControl,
    "tar": rcontrol.LocalTarControl,
    }


class RemoteManager(object):
    def __init__(self):
        self.remotes = {}

    def cleanup(self):
        for remote in self.remotes.values():
            remote.close()

    def get_remote(self, node, method):
        method = method or "ssh"
        key = (node.name, method)
        remote = self.remotes.get(key)
        if not remote:
            parts = method.split(":", 1)
            if len(parts) == 2:
                method, args = parts
                args = [args]
            else:
                args = []
            try:
                control_class = METHODS[method]
            except KeyError:
                raise errors.RemoteError(
                    "unknown remote control method %r" % method)

            remote = control_class(node, *args)
            self.remotes[key] = remote

        return remote

manager = RemoteManager()

get_remote = manager.get_remote
