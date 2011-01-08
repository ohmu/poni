"""
Node remote control using OpenSSH command-line apps

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

import os
import subprocess
from . import rcontrol


class OpenSshRemoteControl(rcontrol.SshRemoteControl):
    """
    OpenSSH remote control connection

    Maintains a shell connection that can be piggy-backed by further ssh or
    scp operations if OpenSSH is configured for shared connections,
    for example:

    .ssh/config:
    ---clip---
       Host *
         ControlPath ~/.ssh/master-%l-%r@%h:%p
         ControlMaster auto
    ---clip---

    """

    def __init__(self, node):
        rcontrol.SshRemoteControl.__init__(self, node)
        self.node = node
        self._shared_conn = None

    def close(self):
        if self._shared_conn:
            self._shared_conn.stdin.close()
            self._shared_conn.stderr.close()
            self._shared_conn.stdout.close()

    def open_shared_connection(self):
        if not self._shared_conn:
            cmd = self.cmd([])
            self._shared_conn = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

    def cmd(self, args):
        assert isinstance(args, list)
        full_key_path = "%s/.ssh/%s" % (os.environ["HOME"], self.key_filename)
        command = [
            "ssh",
            "-i", full_key_path,
            "-l", self.node["user"],
            self.node["host"]
            ]
        command.extend(args)
        return command

    def stat(self, file_path):
        # TODO: implementation
        return None

    def read_file(self, file_path):
        self.open_shared_connection()
        process = subprocess.Popen(self.cmd(["cat", file_path]),
                                   stdout=subprocess.PIPE)
        return process.stdout.read()


    def write_file(self, file_path, contents, mode=None):
        self.open_shared_connection()
        process = subprocess.Popen(self.cmd(["cat", ">", file_path]),
                                   stdin=subprocess.PIPE)
        process.stdin.write(contents)

    def execute_command(self, command):
        self.open_shared_connection()
        return subprocess.call(self.cmd([command]))

    def execute_shell(self):
        self.open_shared_connection()
        return subprocess.call(self.cmd([]))


