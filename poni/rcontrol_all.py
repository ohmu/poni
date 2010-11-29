"""
Node remote control switchboard

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

from . import rcontrol
from . import rcontrol_paramiko
from . import rcontrol_openssh
from . import errors


def get_remote(node):
    # NOTE: assuming that empty "host" means localhost would be dangerous
    host = node.get("host")
    if not host:
        raise errors.RemoteError("%s: 'host' property not set" % node.name)
    elif node.get("host") == "@local":
        return rcontrol.LocalControl(node)
    else:
        return rcontrol_paramiko.ParamikoRemoteControl(node)
        #return rcontrol_openssh.OpenSshRemoteControl(node)


