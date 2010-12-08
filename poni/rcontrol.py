"""
Remote controlling of nodes: copying files, executing commands

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

from __future__ import with_statement

import os
import subprocess
import logging
import shutil
from . import errors


class RemoteControl:
    def __init__(self, node):
        self.node = node

    def close(self):
        pass

    def stat(self, file_path):
        assert 0, "must implement in sub-class"

    def read_file(self, file_path):
        assert 0, "must implement in sub-class"

    def put_file(self, source_path, dest_path, callback=None):
        assert 0, "must implement in sub-class"

    def write_file(self, file_path, contents, mode=None):
        assert 0, "must implement in sub-class"

    def execute(self, command):
        assert 0, "must implement in sub-class"

    def shell(self):
        assert 0, "must implement in sub-class"

    def makedirs(self, dir_path):
        assert 0, "must implement in sub-class"


def convert_local_errors(method):
    """Convert local file-access errors to errors.RemoteError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except (OSError, IOError), error:
            raise errors.RemoteError("%s: %s" % (error.__class__.__name__,
                                                 error))

    wrapper.__doc__ = method.__doc__
    wrapper.__name__ = method.__name__

    return wrapper


class LocalControl(RemoteControl):
    """Local file-system access"""
    def __init__(self, node):
        RemoteControl.__init__(self, node)

    @convert_local_errors
    def put_file(self, source_path, dest_path, callback=None):
        shutil.copy(source_path, dest_path)

    @convert_local_errors
    def makedirs(self, dir_path):
        return os.makedirs(dir_path)

    @convert_local_errors
    def read_file(self, file_path):
        return file(file_path, "rb").read()

    @convert_local_errors
    def write_file(self, file_path, contents, mode=None):
        f = file(file_path, "wb")
        if mode is not None:
            os.chmod(file_path, mode)

        f.write(contents)
        f.close()

    @convert_local_errors
    def execute(self, cmd):
        return subprocess.call(cmd)

    @convert_local_errors
    def shell(self):
        shell = os.environ.get("SHELL")
        if not shell:
            raise errors.RemoteError("$SHELL is not defined")

        return self.execute(["/usr/bin/env", shell])

    @convert_local_errors
    def stat(self, file_path):
        return os.stat(file_path)

    @convert_local_errors
    def utime(self, file_path, times):
        os.utime(file_path, times)


class SshRemoteControl(RemoteControl):
    """Remote control over an SSH connection using Paramiko"""
    def __init__(self, node):
        self.log = logging.getLogger("ssh")
        RemoteControl.__init__(self, node)
        self.key_filename = None
        cloud_key = node.get("cloud", {}).get("key-pair")
        if cloud_key:
            # cloud 'key-pair' overrides 'ssh-key' from host properties
            self.key_filename = "%s.pem" % cloud_key
        else:
            self.key_filename = node.get_tree_property("ssh-key")


