"""
Remote controlling of nodes: copying files, executing commands

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

from __future__ import with_statement

import os
import subprocess
import logging
import shutil
import sys
import select
from . import errors
from . import colors


DONE = 0
STDOUT = 1
STDERR = 2


class RemoteControl:
    def __init__(self, node):
        self.node = node
        self.warn_timeout = 30.0 # seconds to wait before warning user after receiving any output
        self.terminate_timeout = 300.0 # seconds to wait before disconnecting after receiving any output

    def tag_line(self, tag, command, result=None, verbose=False, color=None):
        assert color
        if not verbose:
            return

        desc = "%s (%s): %s" % (color(self.node.name, "node"),
                                color(self.node.get("host"), "host"),
                                color(command, "command"))
        if result is not None:
            tag = "%s (%s)" % (tag, result)

        print color("--- %s" % tag, "header"), desc, color("---", "header")

    def get_color(self, color):
        if color:
            return color
        else:
            return colors.Output(sys.stdout, color="no").color

    def execute(self, command, verbose=False, color=None, output_lines=None):
        color = self.get_color(color)
        self.tag_line("BEGIN", command, verbose=verbose, color=color)
        result = None
        output_chunks = []
        try:
            while True:
                for code, output in self.execute_command(command):
                    if code == STDOUT:
                        if output_lines is not None:
                            output_chunks.append(output)
                        else:
                            sys.stdout.write(output)
                            sys.stdout.flush()
                    elif code == STDERR:
                        sys.stderr.write(output)
                        sys.stderr.flush()
                    else: # DONE
                        if output_lines is not None:
                            output_lines.extend(
                                ("".join(output_chunks)).splitlines())

                        result = output
                        return output
        except Exception, error:
            result = "%s: %s" % (error.__class__.__name__, error)
            raise
        finally:
            self.tag_line("END", command, result=result, verbose=verbose,
                          color=color)

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

    def write_file(self, file_path, contents, mode=None):
        assert 0, "must implement in sub-class"

    def execute_command(self, command):
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
    def execute_command(self, cmd):
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


