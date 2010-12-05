"""
Node remote control switchboard

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

from . import rcontrol
from . import rcontrol_paramiko
from . import rcontrol_openssh
from . import errors

METHODS = {
    "ssh": rcontrol_paramiko.ParamikoRemoteControl,
    "local": rcontrol.LocalControl,
    }

def get_remote(node, method):
    try:
        control_class = METHODS[method or "ssh"]
    except KeyError:
        raise errors.RemoteError("unknown remote control method %r" % method)

    return control_class(node)


