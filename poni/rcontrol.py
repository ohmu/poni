"""
Remote controlling of nodes: copying files, executing commands

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

from __future__ import with_statement

from io import BytesIO
import errno
import logging
import os
import select
import shutil
import subprocess
import sys
import tarfile
import time
from . import errors
from . import colors


DONE = 0
STDOUT = 1
STDERR = 2


class RemoteControl(object):
    def __init__(self, node):
        self.node = node
        self.warn_timeout = 30.0 # seconds to wait before warning user after receiving any output
        self.terminate_timeout = node.get_tree_property("control_timeout", 300.0) # seconds to wait before disconnecting after receiving any output

    def get_out_line(self, color, tag, command, result):
        desc = "%s (%s): %s" % (color(self.node.name, "node"),
                                color(self.node.get("host"), "host"),
                                color(command, "command"))
        if result is not None:
            tag = "%s (%s)" % (tag, result)

        out_line = "%s %s %s %s\n" % (color("---", "header"),
                                      tag,
                                      desc,
                                      color("---", "header"))
        return out_line

    def tag_line(self, tag, command, result=None, verbose=False, color=None,
                 out_file=None):
        assert color
        if out_file and not out_file.isatty():
            no_color = self.get_color(None, out_file=out_file)
            plain_out = self.get_out_line(no_color, tag, command, result)
            out_file.write(plain_out)

        if verbose:
            color_out = self.get_out_line(color, tag, command, result)
            sys.stdout.write(color_out)

    def get_color(self, color, out_file=None):
        out_file = out_file or sys.stdout
        if color:
            return color
        else:
            return colors.Output(out_file, color="no").color

    def execute(self, command, verbose=False, color=None, output_lines=None,
        output_file=None, quiet=False, exec_options=None):
        exec_options = exec_options or {}
        if output_file is not None:
            stdout_file = output_file
            stderr_file = output_file
        elif not quiet:
            stdout_file = sys.stdout
            stderr_file = sys.stderr
        else:
            stdout_file = None
            stderr_file = None

        result = None
        output_chunks = []
        color = self.get_color(color, out_file=stdout_file)
        self.tag_line(color("BEGIN", "header"), command, verbose=verbose,
                      color=color, out_file=stdout_file)

        start = time.time()
        try:
            while True:
                for code, output in self.execute_command(command,
                        **exec_options):
                    if code == STDOUT:
                        if output_lines is not None:
                            output_chunks.append(output)
                        elif stdout_file:
                            if not verbose or stdout_file:
                                stdout_file.write(output)
                            else:
                                for line in output.splitlines(True):
                                    stdout_file.write(
                                        "[%s] %s" % (color(self.node.name,
                                                           "node"), line))
                            stdout_file.flush()
                    elif code == STDERR:
                        if not verbose or stdout_file:
                            stderr_file.write(output)
                        elif stderr_file:
                            for line in output.splitlines(True):
                                stderr_file.write(
                                    "{%s} %s" % (color(self.node.name,
                                                       "node"), line))
                        stderr_file.flush()
                    else: # DONE
                        if output_lines is not None:
                            output_lines.extend(
                                ("".join(output_chunks)).splitlines())

                        if not output:
                            result = color("OK", "op_ok")
                        else:
                            result = color(output, "op_error")
                        return output
        except Exception as error:
            result = color("%s: %s" % (error.__class__.__name__, error),
                           "op_error")
            raise
        finally:
            elapsed = time.time() - start
            self.tag_line(color("END %.1fs" % elapsed, "header"), command, result=result,
                          verbose=verbose, color=color, out_file=stdout_file)

    def shell(self, verbose=False, color=None):
        color = self.get_color(color)
        self.tag_line("BEGIN", "shell", verbose=verbose, color=color)
        try:
            return self.execute_shell()
        finally:
            self.tag_line("END", "shell", verbose=verbose, color=color)

    def close(self):
        pass

    def stat(self, file_path):
        assert 0, "must implement in sub-class"

    def read_file(self, file_path):
        assert 0, "must implement in sub-class"

    def put_file(self, source_path, dest_path, callback=None):
        assert 0, "must implement in sub-class"

    def write_file(self, file_path, contents, mode=None, owner=None,
                   group=None):
        assert 0, "must implement in sub-class"

    def execute_command(self, command, pseudo_tty=False):
        assert 0, "must implement in sub-class"

    def execute_shell(self):
        assert 0, "must implement in sub-class"

    def makedirs(self, dir_path):
        assert 0, "must implement in sub-class"


def convert_local_errors(method):
    """Convert local file-access errors to errors.RemoteError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except IOError as error:
            if error.errno == errno.ENOENT:
                raise errors.RemoteFileDoesNotExist(str(error))
            else:
                raise errors.RemoteError("%s: %s" % (error.__class__.__name__,
                                                     error))
        except OSError as error:
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
        return open(file_path, "rb").read()

    @convert_local_errors
    def write_file(self, file_path, contents, mode=None, owner=None,
                   group=None):
        f = open(file_path, "wb" if isinstance(contents, bytes) else "w")
        if mode is not None:
            os.chmod(file_path, mode)

        if (owner is not None) or (group is not None):
            # set owner and group
            file_stat = os.stat(file_path)
            os.chown(file_path,
                     owner if (owner is not None) else file_stat.st_uid,
                     group if (group is not None) else file_stat.st_gid)

        f.write(contents)
        f.close()

    @convert_local_errors
    def execute_command(self, cmd, pseudo_tty=False):
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        fds = [process.stdout, process.stderr]
        CHUNK = 2**20
        while process.poll() is None:
            r, w, e = select.select(fds, [], fds)
            if process.stdout in r:
                yield STDOUT, process.stdout.read(CHUNK)

            if process.stderr in r:
                yield STDERR, process.stderr.read(CHUNK)

        yield DONE, process.returncode

    @convert_local_errors
    def execute_shell(self):
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


class LocalTarControl(RemoteControl):
    """Writing to a local tar file"""
    def __init__(self, node, tar_dir):
        self.tar_dir = tar_dir
        RemoteControl.__init__(self, node)

    @convert_local_errors
    def put_file(self, source_path, dest_path, callback=None):
        self.write_file(dest_path, open(source_path, "rb").read())

    @convert_local_errors
    def makedirs(self, dir_path):
        pass

    @convert_local_errors
    def read_file(self, file_path):
        raise IOError(errno.ENOENT, "LocalTarControl: No such file")

    @convert_local_errors
    def write_file(self, file_path, contents, mode=None, owner=None,
                   group=None):
        full_path = os.path.join(self.tar_dir, self.node["host"], "image.tar")
        if not os.path.isdir(os.path.dirname(full_path)):
            os.makedirs(os.path.dirname(full_path))

        file_obj = BytesIO(contents)
        with tarfile.open(full_path, "a") as output:
            info = tarfile.TarInfo(file_path)
            info.size = len(contents)
            if mode is not None:
                info.mode = mode
            if owner is not None:
                info.uid = owner
            if group is not None:
                info.gid = group
            info.mtime = time.time()
            output.addfile(info, file_obj)

    @convert_local_errors
    def execute_command(self, cmd, pseudo_tty=False):
        full_path = os.path.join(self.tar_dir, self.node["host"], "image.control")
        if not os.path.isdir(os.path.dirname(full_path)):
            os.makedirs(os.path.dirname(full_path))

        with open(full_path, "a") as output:
            output.write(cmd + "\n")

        yield DONE, 0

    @convert_local_errors
    def execute_shell(self):
        assert 0, "LocalTarControl does not support remote commands"

    @convert_local_errors
    def stat(self, file_path):
        raise IOError(errno.ENOENT, "LocalTarControl: No such file")

    @convert_local_errors
    def utime(self, file_path, times):
        pass


class SshRemoteControl(RemoteControl):
    """Remote control over an SSH connection using Paramiko"""
    def __init__(self, node):
        self.log = logging.getLogger("ssh")
        RemoteControl.__init__(self, node)
        self.key_filename = None
        cloud_prop = node.get("cloud", {})
        # renamed property name: backward-compatibility
        cloud_key = cloud_prop.get("key_pair", cloud_prop.get("key-pair"))
        if cloud_key:
            # cloud 'key_pair' overrides 'ssh-key' from host properties
            self.key_filename = "%s.pem" % cloud_key
        else:
            self.key_filename = node.get_tree_property("ssh-key")

        self.connect_timeout = node.get_tree_property("ssh-timeout", 60.0)
