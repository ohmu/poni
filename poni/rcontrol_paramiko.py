"""
Remote node control using the Paramiko SSH library

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

import os
import sys
import socket
import time
from . import errors
from . import rcontrol
import select
import termios
import tty
from path import path

import warnings
try:
    with warnings.catch_warnings():
        # paramiko needs to be imported with warnings disabled to get rid of
        # a useless (really) crypto warning
        warnings.simplefilter("ignore")
        import paramiko
except AttributeError:
    import paramiko


def convert_paramiko_errors(method):
    """Convert remote Paramiko errors to errors.RemoteError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except (socket.error, paramiko.SSHException, IOError), error:
            # TODO: should IOError be catched here?
            raise errors.RemoteError("%s: %s" % (error.__class__.__name__,
                                                 error))

    wrapper.__doc__ = method.__doc__
    wrapper.__name__ = method.__name__

    return wrapper


def interactive_shell(chan):
    """stolen from paramiko examples"""
    oldtty = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        chan.settimeout(0.0)

        while True:
            r, w, e = select.select([chan, sys.stdin], [], [])
            if chan in r:
                try:
                    x = chan.recv(1024)
                    if len(x) == 0:
                        break
                    sys.stdout.write(x)
                    sys.stdout.flush()
                except socket.timeout:
                    pass
            if sys.stdin in r:
                x = sys.stdin.read(1)
                if len(x) == 0:
                    break
                chan.send(x)

    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)


class ParamikoRemoteControl(rcontrol.SshRemoteControl):
    def __init__(self, node):
        rcontrol.SshRemoteControl.__init__(self, node)
        self._ssh = None
        self._sftp = None

    def get_sftp(self):
        if not self._sftp:
            self._sftp = self.get_ssh().open_sftp()

        return self._sftp

    @convert_paramiko_errors
    def read_file(self, file_path):
        file_path = str(file_path)
        sftp = self.get_sftp()
        return sftp.file(file_path, mode="rb").read()

    @convert_paramiko_errors
    def write_file(self, file_path, contents, mode=None):
        file_path = str(file_path)
        sftp = self.get_sftp()
        f = sftp.file(file_path, mode="wb")
        if mode is not None:
            sftp.chmod(file_path, mode)

        f.write(contents)
        f.close()

    def close(self):
        if self._sftp:
            self._sftp.close()
            self._sftp = None

        if self._ssh:
            self._ssh.close()
            self._ssh = None

    def get_ssh(self):
        if self._ssh:
            return self._ssh

        host = self.node.get("host")
        user = self.node.get("user")

        if not host:
            raise errors.RemoteError("%s: 'host' property not defined" % (
                        self.node.name))
        elif not user:
            raise errors.RemoteError("%s: 'user' property not defined" % (
                self.node.name))

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if self.key_filename:
            # TODO: other dirs than ~/.ssh/
            key_file = "%s/.ssh/%s" % (os.environ.get("HOME"),
                                       self.key_filename)
        else:
            key_file = None

        self.log.debug("ssh connect: host=%s, user=%s, key=%s",
                       host, user, key_file)

        retries = 10
        while True:
            try:
                ssh.connect(host, username=user, key_filename=key_file)
                break
            except (socket.error, paramiko.SSHException), error:
                self.log.warning("ssh connection to %r failed: %s: %s, "
                                 "retries remaining=%s" % (
                                  host, error.__class__.__name__,
                                     error, retries))

                if retries == 0:
                    raise

                time.sleep(3)
                retries -= 1

        self._ssh = ssh

        return self._ssh

    @convert_paramiko_errors
    def execute_command(self, cmd):
        ssh = self.get_ssh()
        transport = ssh.get_transport()
        channel = transport.open_session()
        BS = 2**16
        try:
            channel.exec_command(cmd)
            reading = True
            while reading:
                r, w, e = select.select([channel], [], [])
                if channel.recv_stderr_ready():
                    # TODO: will this catch all stderr output?
                    x = channel.recv_stderr(BS)
                    if x:
                        yield rcontrol.STDERR, x

                for file_out in r:
                    x = file_out.recv(BS)
                    if len(x) == 0:
                        reading = False
                        break

                    yield rcontrol.STDOUT, x

            exit_code = channel.recv_exit_status()
        finally:
            if channel.recv_stderr_ready():
                # TODO: will this catch all stderr output?
                x = channel.recv_stderr(BS)
                if x:
                    yield rcontrol.STDERR, x

            channel.close()

        yield rcontrol.DONE, exit_code

    @convert_paramiko_errors
    def execute_shell(self):
        ssh = self.get_ssh()
        channel = None
        try:
            channel = ssh.invoke_shell(term='vt100',
                                       width=80, height=24) # TODO: dimensions?
            interactive_shell(channel)
        finally:
            if channel:
                channel.close()

    @convert_paramiko_errors
    def stat(self, file_path):
        file_path = str(file_path)
        sftp = self.get_sftp()
        return sftp.stat(file_path)

    @convert_paramiko_errors
    def put_file(self, source_path, dest_path, callback=None):
        source_path = str(source_path)
        dest_path = str(dest_path)
        sftp = self.get_sftp()
        sftp.put(source_path, dest_path, callback=callback)

    @convert_paramiko_errors
    def makedirs(self, dir_path):
        dir_path = path(dir_path)
        sftp = self.get_sftp()
        create_dirs = []
        while 1:
            try:
                sftp.stat(str(dir_path))
                break # dir exists
            except (paramiko.SSHException, IOError):
                create_dirs.insert(0, dir_path)
                dir_path, rest = dir_path.splitpath()
                if not dir_path or not rest:
                    break

        for dir_path in create_dirs:
            sftp.mkdir(str(dir_path))

    @convert_paramiko_errors
    def utime(self, file_path, times):
        sftp = self.get_sftp()
        sftp.utime(str(file_path), times)
