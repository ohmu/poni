"""
Remote node control using the Paramiko SSH library

Copyright (c) 2010-2012 Mika Eloranta
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
import errno

import warnings
try:
    with warnings.catch_warnings():
        # paramiko needs to be imported with warnings disabled to get rid of
        # a useless (really) crypto warning
        warnings.simplefilter("ignore")
        import paramiko
except AttributeError:
    import paramiko

try:
    from select import epoll
except ImportError:
    epoll = None


def convert_paramiko_errors(method):
    """Convert remote Paramiko errors to errors.RemoteError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except IOError as error:
            if error.errno == errno.ENOENT:
                raise errors.RemoteFileDoesNotExist(str(error))
            else:
                raise errors.RemoteError("%s: %s" % (error.__class__.__name__,
                                                     error))
        except (socket.error, paramiko.SSHException, EOFError) as error:
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
        self.ping_interval = 10

    def get_sftp(self):
        if not self._sftp:
            self._sftp = self.get_ssh(lambda ssh: ssh.open_sftp())
        return self._sftp

    @convert_paramiko_errors
    def read_file(self, file_path):
        file_path = str(file_path)
        sftp = self.get_sftp()
        return sftp.file(file_path, mode="rb").read()

    @convert_paramiko_errors
    def write_file(self, file_path, contents, mode=None, owner=None,
                   group=None):
        file_path = str(file_path)
        sftp = self.get_sftp()
        f = sftp.file(file_path, mode="wb")
        if mode is not None:
            sftp.chmod(file_path, mode)

        if (owner is not None) or (group is not None):
            # set owner and group
            file_stat = sftp.stat(file_path)
            sftp.chown(file_path,
                       owner if (owner is not None) else file_stat.st_uid,
                       group if (group is not None) else file_stat.st_gid)

        f.write(contents)
        f.close()

    def close(self):
        if self._sftp:
            self._sftp.close()
            self._sftp = None

        if self._ssh:
            self._ssh.close()
            self._ssh = None

    def get_ssh(self, action=None):
        host = self.node.get("host")
        user = self.node.get("user")
        password = self.node.get("password")
        port = int(self.node.get("ssh-port", os.environ.get("PONI_SSH_PORT", 22)))

        if not host:
            raise errors.RemoteError("%s: 'host' property not defined" % (
                        self.node.name))
        elif not user:
            raise errors.RemoteError("%s: 'user' property not defined" % (
                self.node.name))

        if self.key_filename:
            key_file = self.key_filename
            if not os.path.isabs(key_file):
                key_file = "%s/.ssh/%s" % (os.environ.get("HOME"),
                                           key_file)
        else:
            key_file = None

        self.log.debug("ssh connect: host=%s, port=%r, user=%s, key=%s",
                       host, port, user, key_file)

        end_time = time.time() + self.connect_timeout
        while time.time() < end_time:
            try:
                if not self._ssh:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(host, port=port, username=user, key_filename=key_file, password=password)
                    self._ssh = ssh
                return action(self._ssh) if action else self._ssh
            except (socket.error, paramiko.SSHException) as error:
                remaining = max(0, end_time - time.time())
                self.log.warning("%s: ssh connection to %s failed: %s: %s, "
                                 "retry time remaining=%.0fs",
                                 self.node.name, host,
                                 error.__class__.__name__, error, remaining)
                self._ssh = None
                time.sleep(2.5)

        raise errors.RemoteError("%s: ssh connect failed: %s: %s" % (
                self.node.name, error.__class__.__name__, error))

    @convert_paramiko_errors
    def execute_command(self, cmd, pseudo_tty=False):
        def get_channel(ssh):
            channel = ssh.get_transport().open_session()
            if not channel:
                raise paramiko.SSHException("channel opening failed")
            return channel
        channel = self.get_ssh(get_channel)
        if not channel:
            raise errors.RemoteError("failed to open an SSH session to %s" % (
                    self.node.name))
        if pseudo_tty:
            channel.get_pty()

        channel.set_combine_stderr(True) # TODO: separate stdout/stderr?
        BS = 2**16
        rx_time = time.time()
        log_name = "%s (%s): %r" % (self.node.name, self.node.get("host"), cmd)
        next_warn = time.time() + self.warn_timeout
        next_ping = time.time() + self.ping_interval

        def available_output():
            """read all the output that is immediately available"""
            while channel.recv_ready():
                chunk = channel.recv(BS)
                yield rcontrol.STDOUT, chunk

        channel.exec_command(cmd)
        channel.shutdown_write()

        exit_code = None
        if epoll:
            poll = select.epoll()
            poll.register(channel.fileno(), select.EPOLLIN)
        else:
            poll = None

        try:
            while True:
                if (exit_code is None) and channel.exit_status_ready():
                    # process has finished executing, but there still may be
                    # output to read from stdout or stderr
                    exit_code = channel.recv_exit_status()

                # wait for input, note that the results are not used for anything
                if poll:
                    try:
                        poll.poll(timeout=1.0)  # just poll, not interested in the fileno
                    except IOError as ex:
                        if ex.errno != errno.EINTR:
                            raise
                        continue
                else:
                    select.select([channel], [], [], 1.0)

                for output in available_output():
                    rx_time = time.time()
                    next_warn = time.time() + self.warn_timeout
                    yield output

                if channel.closed and (exit_code is not None):
                    yield rcontrol.DONE, exit_code
                    break  # everything done!

                now = time.time()
                if now > (rx_time + self.terminate_timeout):
                    # no output in a long time, terminate connection
                    raise errors.RemoteError(
                        "%s: no output in %.1f seconds, terminating" % (
                            log_name, self.terminate_timeout))

                if now > next_warn:
                    elapsed_since = time.time() - rx_time
                    self.log.warning("%s: no output in %.1fs", log_name,
                                     elapsed_since)
                    next_warn = time.time() + self.warn_timeout

                if now > next_ping:
                    channel.transport.send_ignore()
                    next_ping = time.time() + self.ping_interval
        finally:
            if poll:
                poll.close()

    @convert_paramiko_errors
    def execute_shell(self):
        def invoke_shell(ssh):
            # TODO: get dimensions from `stty size` or something like that
            return ssh.invoke_shell(term='vt100', width=80, height=24)
        try:
            channel = self.get_ssh(invoke_shell)
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
        sftp = self.get_sftp()
        create_dirs = []
        while 1:
            try:
                sftp.stat(dir_path)
                break # dir exists
            except (paramiko.SSHException, IOError):
                create_dirs.insert(0, dir_path)
                dir_path, rest = os.path.split(dir_path)
                if not dir_path or not rest:
                    break

        for dir_path in create_dirs:
            sftp.mkdir(dir_path)

    @convert_paramiko_errors
    def utime(self, file_path, times):
        sftp = self.get_sftp()
        sftp.utime(str(file_path), times)
