"""
config rendering and verification

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

import sys
import itertools
import datetime
import logging
import difflib
from path import path
from . import errors
from . import util
from . import colors

import Cheetah.Template
from Cheetah.Template import Template as CheetahTemplate


class Manager:
    def __init__(self, confman):
        self.log = logging.getLogger("manager")
        self.files = []
        self.error_count = 0
        self.confman = confman
        self.dynamic_conf = []
        self.audit_format = "%8s %s: %s"

    def add_dynamic(self, item):
        self.dynamic_conf.append(item)

    def emit_error(self, node, source_path, error):
        self.log.warning("node %s: %s: %s: %s", node.name, source_path,
                         error.__class__.__name__, error)
        self.error_count += 1

    def copy_tree(self, entry, remote):
        def progress(copied, total):
            sys.stderr.write("\r%s/%s bytes copied" % (copied, total))

        dest_dir = path(entry["dest_path"])
        try:
            remote.stat(dest_dir)
        except errors.RemoteError:
            remote.makedirs(dest_dir)

        for file_path in path(entry["source_path"]).files():
            dest_path = dest_dir / file_path.basename()
            lstat = file_path.stat()
            try:
                rstat = remote.stat(dest_path)
                # copy if mtime or size differs
                copy = ((lstat.st_size != rstat.st_size)
                        or (lstat.st_mtime != rstat.st_mtime))
            except errors.RemoteError:
                copy = True

            if copy:
                self.log.info("copying: %s", dest_path)
                remote.put_file(file_path, dest_path, callback=progress)
                remote.utime(dest_path, (int(lstat.st_mtime),
                                         int(lstat.st_mtime)))
                sys.stderr.write("\n")
            else:
                self.log.info("already copied: %s", dest_path)

    def verify(self, show=False, deploy=False, audit=False, show_diff=False,
               verbose=False, callback=None, path_prefix="", raw=False,
               access_method=None, color="auto"):
        self.log.debug("verify: %s", dict(show=show, deploy=deploy,
                                          audit=audit, show_diff=show_diff,
                                          verbose=verbose, callback=callback))
        files = [f for f in self.files if not f.get("report")]
        reports = [f for f in self.files if f.get("report")]
        if path_prefix and not path_prefix.endswith("/"):
            path_prefix += "/"

        color = colors.Output(sys.stdout, color=color).color
        error_count = 0
        for entry in itertools.chain(files, reports):
            if not entry["node"].verify_enabled():
                self.log.debug("filtered: verify disabled: %r", entry)
                continue

            if callback and not callback(entry):
                self.log.debug("filtered: callback: %r", entry)
                continue

            self.log.debug("verify: %r", entry)
            render = entry["render"]
            failed = False
            node_name = entry["node"].name

            if entry["type"] == "dir":
                if deploy:
                    # copy a directory recursively
                    remote = entry["node"].get_remote(override=access_method)
                    self.copy_tree(entry, remote)
                else:
                    # verify
                    try:
                        dir_stats = util.dir_stats(entry["source_path"])
                    except (OSError, IOError), error:
                        raise errors.VerifyError(
                            "cannot copy files from '%s': %s: %s"% (
                                error.__class__.__name__, error))

                    if dir_stats["file_count"] == 0:
                        self.log.warning("source directory '%s' is empty" % (
                                entry["source_path"]))
                    elif verbose:
                        self.log.info(
                            "[OK] copy source directory '%(path)s' has "
                            "%(file_count)s files, "
                            "%(total_bytes)s bytes" % dir_stats)

                # dir handled, next!
                continue

            source_path = entry["config"].path / entry["source_path"]
            try:
                dest_path = entry["dest_path"]
                if dest_path[-1:] == "/":
                    # dest path ending in slash: use source filename
                    dest_path = path(dest_path) / source_path.basename()

                if raw:
                    dest_path, output = dest_path, source_path.bytes()
                else:
                    dest_path, output = render(source_path, dest_path)

                dest_path = path(path_prefix + dest_path).normpath()
                if verbose:
                    self.log.info("[OK] file: %s", dest_path)
            except Exception, error:
                self.emit_error(entry["node"], source_path, error)
                output = util.format_error(error)
                failed = True
                error_count += 1

            if show:
                identity = "%s%s%s" % (color(node_name, "node"),
                                       color(": path=", "header"),
                                       color(dest_path, "path"))
                print color("--- BEGIN", "header"), identity, \
                    color("---", "header")
                print output
                print color("--- END", "header"), identity, \
                    color("---", "header")
                print

            remote = None

            if (audit or deploy) and dest_path and (not failed):
                # read existing file
                try:
                    remote = entry["node"].get_remote(override=access_method)
                    active_text = remote.read_file(dest_path)
                    stat = remote.stat(dest_path)
                    if stat:
                        active_time = datetime.datetime.fromtimestamp(
                            stat.st_mtime)
                    else:
                        active_time = ""
                except errors.RemoteError, error:
                    if audit:
                        self.log.error("%s: %s: %s: %s", node_name, dest_path,
                                       error.__class__.__name__, error)
                        error_count += 1

                    active_text = None
            else:
                active_text = None

            if active_text and audit:
                self.audit_output(entry, dest_path, active_text, active_time,
                                  output, show_diff=show_diff)

            if deploy and dest_path and (not failed):
                remote = entry["node"].get_remote(override=access_method)
                try:
                    self.deploy_file(remote, entry, dest_path, output,
                                     active_text, verbose=verbose,
                                     mode=entry.get("mode"))
                except errors.RemoteError, error:
                    error_count += 1
                    self.log.error("%s: %s: %s", node_name, dest_path, error)
                    # NOTE: continuing

        if error_count:
            raise errors.VerifyError("failed: there were %s errors" % (
                    error_count))

    def deploy_file(self, remote, entry, dest_path, output, active_text,
                    verbose=False, mode=None):
        if output == active_text:
            # nothing to do
            if verbose:
                self.log.info(self.audit_format, "OK",
                              entry["node"].name, dest_path)

            return

        dest_dir = dest_path.dirname()
        try:
            remote.stat(dest_dir)
        except errors.RemoteError:
            remote.makedirs(dest_dir)

        remote.write_file(dest_path, output, mode=mode)
        post_process = entry.get("post_process")
        if post_process:
            # TODO: remote support
            post_process(dest_path)

        self.log.info(self.audit_format, "WROTE",
                      entry["node"].name, dest_path)

    def audit_output(self, entry, dest_path, active_text, active_time,
                     output, show_diff=False):
        if (active_text is not None) and (active_text != output):
            self.log.warning(self.audit_format, "DIFFERS",
                             entry["node"].name, dest_path)
            if show_diff:
                diff = difflib.unified_diff(
                    output.splitlines(True),
                    active_text.splitlines(True),
                    "config", "active",
                    "TODO:mtime", active_time,
                    lineterm="\n")

                for line in diff:
                    print line,
        elif active_text:
            self.log.info(self.audit_format, "OK", entry["node"].name,
                          dest_path)

    def add_file(self, **kw):
        self.log.debug("add_file: %s", kw)
        self.files.append(kw)


class PlugIn:
    def __init__(self, manager, config, node, top_config):
        self.log = logging.getLogger("plugin")
        self.manager = manager
        self.config = config
        self.top_config = top_config
        self.node = node

    def add_file(self, source_path, dest_path=None, source_text=None,
                 render=None, report=False, post_process=None, mode=None):
        render = render or self.render_cheetah
        return self.manager.add_file(node=self.node, config=self.config,
                                     type="file", dest_path=dest_path,
                                     source_path=source_path,
                                     source_text=source_text,
                                     render=render, report=report,
                                     post_process=post_process,
                                     mode=mode)

    def add_dir(self, source_path, dest_path, render=None):
        render = render or self.render_cheetah
        return self.manager.add_file(type="dir", node=self.node,
                                     config=self.config, dest_path=dest_path,
                                     source_path=source_path, render=render)

    def get_one(self, name, nodes=True, systems=False):
        hits = list(self.manager.confman.find(name, nodes=nodes,
                                              systems=systems))
        names = (h.name for h in hits)
        assert len(hits) == 1, "found more than one (%d) %r: %s" % (
            len(hits), name, ", ".join(names))

        return hits[0]

    def get_system(self, name):
        return self.get_one(name, nodes=False, systems=True)

    def add_edge(self, source, dest, **kwargs):
        self.manager.add_dynamic(dict(type="edge", source=source, dest=dest,
                                      **kwargs))

    def render_text(self, source_path, dest_path):
        try:
            return dest_path, file(source_path, "rb").read()
        except (IOError, OSError), error:
            raise errors.VerifyError(source_path, error)

    def render_cheetah(self, source_path, dest_path):
        try:
            names = dict(node=self.node,
                         s=self.top_config.settings,
                         settings=self.top_config.settings,
                         system=self.node.system,
                         find=self.manager.confman.find,
                         get_node=self.get_one,
                         get_system=self.get_system,
                         config=self.top_config,
                         edge=self.add_edge,
                         plugin=self,
                         dynconf=self.manager.dynamic_conf)
            text = str(CheetahTemplate(file=source_path, searchList=[names]))
            if dest_path:
                dest_path = str(CheetahTemplate(dest_path, searchList=[names]))

            return dest_path, text
        except Cheetah.Template.Error, error:
            raise errors.VerifyError(source_path, error)

