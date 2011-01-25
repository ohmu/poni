"""
config rendering and verification

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

import sys
import itertools
import datetime
import logging
import difflib
from path import path
import argh
import argparse
from . import errors
from . import util
from . import colors

import Cheetah.Template
from Cheetah.Template import Template as CheetahTemplate

try:
    import genshi
    import genshi.template
except ImportError:
    genshi = None


class Manager:
    def __init__(self, confman):
        self.log = logging.getLogger("manager")
        self.files = []
        self.error_count = 0
        self.confman = confman
        self.buckets = {}
        self.audit_format = "%8s %s: %s"

    def get_bucket(self, name):
        return self.buckets.setdefault(name, [])

    def emit_error(self, node, source_path, error):
        self.log.warning("node %s: %s: %s: %s", node.name, source_path,
                         error.__class__.__name__, error)
        self.error_count += 1

    def copy_tree(self, entry, remote, path_prefix="", verbose=False):
        def progress(copied, total):
            sys.stderr.write("\r%s/%s bytes copied" % (copied, total))

        dest_dir = path(path_prefix + entry["dest_path"])
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
            elif verbose:
                self.log.info("already copied: %s", dest_path)

    def verify(self, show=False, deploy=False, audit=False, show_diff=False,
               verbose=False, callback=None, path_prefix="", raw=False,
               access_method=None, color_mode="auto"):
        self.log.debug("verify: %s", dict(show=show, deploy=deploy,
                                          audit=audit, show_diff=show_diff,
                                          verbose=verbose, callback=callback))
        files = [f for f in self.files if not f.get("report")]
        reports = [f for f in self.files if f.get("report")]

        color = colors.Output(sys.stdout, color=color_mode).color
        error_count = 0
        for entry in itertools.chain(files, reports):
            if not entry["node"].verify_enabled():
                self.log.debug("filtered: verify disabled: %r", entry)
                continue

            filtered_out = False
            if callback and not callback(entry):
                self.log.debug("filtered: callback: %r", entry)
                filtered_out = True

            if path_prefix:
                item_path_prefix = "%s/%s/" % (path_prefix, entry["node"].name)
            else:
                item_path_prefix = ""

            self.log.debug("verify: %r", entry)
            render = entry["render"]
            failed = False
            node_name = entry["node"].name

            if entry["type"] == "dir":
                if filtered_out:
                    # ignore
                    pass
                elif deploy:
                    # copy a directory recursively
                    remote = entry["node"].get_remote(override=access_method)
                    self.copy_tree(entry, remote, path_prefix=item_path_prefix,
                                   verbose=verbose)
                else:
                    # verify
                    try:
                        dir_stats = util.dir_stats(entry["source_path"])
                    except (OSError, IOError), error:
                        raise errors.VerifyError(
                            "cannot copy files from '%s': %s: %s"% (
                                entry["source_path"], error.__class__.__name__, error))

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

                dest_path = path(item_path_prefix + dest_path).normpath()
                if (not audit and not deploy) and verbose:
                    # plain verify mode
                    self.log.info("OK: %s file: %s", node_name, dest_path)
            except (IOError, errors.Error), error:
                self.emit_error(entry["node"], source_path, error)
                output = util.format_error(error)
                failed = True
                error_count += 1

            if show and not filtered_out:
                if show_diff:
                    diff = difflib.unified_diff(
                        source_path.bytes().splitlines(True),
                        output.splitlines(True),
                        "template", "rendered",
                        "", "",
                        lineterm="\n")

                    show_output = diff

                else:
                    show_output = output

                identity = "%s%s%s" % (color(node_name, "node"),
                                       color(": path=", "header"),
                                       color(dest_path, "path"))
                sys.stdout.write("%s %s %s\n" % (color("--- BEGIN", "header"),
                                               identity,
                                               color("---", "header")))

                if isinstance(show_output, (str, unicode)):
                    print show_output
                else:
                    diff_colors = {"+": "lgreen", "@": "white", "-": "lred"}
                    for line in show_output:
                        sys.stdout.write(
                            color(line, diff_colors.get(line[:1], "reset")))

                sys.stdout.write("%s %s %s\n\n" % (color("--- END", "header"),
                                                   identity,
                                                   color("---", "header")))
                sys.stdout.flush()

            remote = None

            if (audit or deploy) and dest_path and (not failed) and (not filtered_out):
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
                                  output, show_diff=show_diff,
                                  color_mode=color_mode, verbose=verbose)

            if deploy and dest_path and (not failed) and (not filtered_out):
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
                     output, show_diff=False, color_mode="auto",
                     verbose=False):
        if (active_text is not None) and (active_text != output):
            self.log.warning(self.audit_format, "DIFFERS",
                             entry["node"].name, dest_path)
            if show_diff:
                color = colors.Output(sys.stdout, color=color_mode).color
                diff = difflib.unified_diff(
                    output.splitlines(True),
                    active_text.splitlines(True),
                    "config", "active",
                    "", active_time, # TODO: mtime for config?
                    lineterm="\n")

                diff_colors = {"+": "lgreen", "@": "white", "-": "lred"}
                for line in diff:
                    sys.stdout.write(
                        color(line, diff_colors.get(line[:1], "reset")))

                sys.stdout.flush()
        elif active_text and verbose:
            self.log.info(self.audit_format, "OK", entry["node"].name,
                          dest_path)

    def add_file(self, **kw):
        self.files.append(kw)


def control(provides=None, requires=None):
    """decorate a PlugIn method as a 'poni control' command"""
    def wrap(method):
        method.poni_control = dict(provides=provides, requires=requires)
        return method

    return wrap

class PlugIn:
    def __init__(self, manager, config, node, top_config):
        self.log = logging.getLogger("plugin")
        self.manager = manager
        self.config = config
        self.top_config = top_config
        self.node = node
        self.controls = {}

    def remote_execute(self, arg, script_path):
        for line in self.remote_gen_execute(arg, script_path):
            pass

    def remote_gen_execute(self, arg, script_path, yield_stdout=False):
        """
        run a single remote shell-script, raise ControlError on non-zero
        exit-code, optionally yields stdout line-per-line
        """
        names = self.get_names()
        if isinstance(script_path, (list, tuple)):
            script_path = " ".join(script_path)

        rendered_path = str(CheetahTemplate(script_path,
                                            searchList=[self.get_names()]))

        remote = arg.node.get_remote(override=arg.method)
        lines = [] if yield_stdout else None
        exit_code = remote.execute(rendered_path, verbose=arg.verbose,
                                   output_lines=lines)
        if exit_code:
            raise errors.ControlError("%r failed with exit code %r" % (
                    rendered_path, exit_code))

        for line in (lines or []):
            yield line

    def add_argh_control(self, handler, provides=None, requires=None):
        try:
            name = handler.argh_alias
        except AttributeError:
            name = handler.__name__

        def handle_control(control_name, args, **kwargs):
            return self.handle_argh_control(handler, control_name, args,
                                            **kwargs)

        name = name.replace("_", "-")
        self.controls[name] = dict(callback = handle_control,
                                   plugin = self,
                                   node = self.node,
                                   config = self.config,
                                   provides = provides or [],
                                   requires = requires or [])

    def add_all_controls(self):
        self.add_controls()

        # add controls defined using the 'control' decorator
        for name, prop in self.__class__.__dict__.iteritems():
            if hasattr(prop, "poni_control"):
                self.add_argh_control(getattr(self, prop.__name__),
                                      **prop.poni_control)

    def add_controls(self):
        # overridden in subclass
        pass

    def iter_control_operations(self, node, config):
        for name, prop in self.controls.iteritems():
            out = prop.copy()
            out["name"] = name
            out["config"] = config
            out["node"] = node
            yield out

    def handle_argh_control(self, handler, control_name, args, verbose=False,
                            method=None, send_output=None, node=None):
        assert node
        parser = argh.ArghParser(prog="control")
        parser.add_commands([handler])
        full_args = [control_name] + args
        namespace = argparse.Namespace()
        namespace.verbose = verbose
        namespace.method = method
        namespace.send_output = send_output
        namespace.node = node
        parser.dispatch(argv=full_args, namespace=namespace)

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
                                              systems=systems,
                                              full_match=True))
        names = (h.name for h in hits)
        if len(hits) > 1:
            raise errors.VerifyError("found more than one (%d) %r: %s" % (
                    len(hits), name, ", ".join(names)))
        elif len(hits) == 0:
            raise errors.VerifyError("did not find %r: %s" % (
                    name, ", ".join(names)))

        return hits[0]

    def get_system(self, name):
        return self.get_one(name, nodes=False, systems=True)

    def render_text(self, source_path, dest_path):
        try:
            # paths are always rendered as templates
            dest_path = self.render_cheetah(None, dest_path)[0]
            return dest_path, file(source_path, "rb").read()
        except (IOError, OSError), error:
            raise errors.VerifyError(source_path, error)

    def add_edge(self, bucket_name, dest_node, dest_config, **kwargs):
        self.manager.get_bucket(bucket_name).append(
            dict(source_node=self.node, source_config=self.top_config,
                 dest_node=dest_node, dest_config=dest_config, **kwargs))

    def get_names(self):
        names = dict(node=self.node,
                     s=self.top_config.settings,
                     settings=self.top_config.settings,
                     system=self.node.system,
                     find=self.manager.confman.find,
                     find_config=self.manager.confman.find_config,
                     get_node=self.get_one,
                     get_system=self.get_system,
                     get_config=self.manager.confman.get_config,
                     config=self.top_config,
                     bucket=self.manager.get_bucket,
                     edge=self.add_edge,
                     plugin=self)
        return names

    def render_cheetah(self, source_path, dest_path):
        names = self.get_names()
        # TODO: template caching
        try:
            if source_path is not None:
                text = str(CheetahTemplate(file=source_path,
                                           searchList=[names]))
            else:
                text = None

            if dest_path:
                dest_path = str(CheetahTemplate(dest_path, searchList=[names]))

            return dest_path, text
        except (Cheetah.Template.Error, SyntaxError,
                Cheetah.NameMapper.NotFound), error:
            raise errors.VerifyError("%s: %s: %s" % (
                source_path, error.__class__.__name__, error))

    def render_genshi_xml(self, source_path, dest_path):
        assert genshi, "Genshi is not installed"

        names = self.get_names()
        if dest_path:
            dest_path = str(CheetahTemplate(dest_path, searchList=[names]))

        try:
            tmpl = genshi.template.MarkupTemplate(file(source_path),
                                                  filepath=source_path)
            stream = tmpl.generate(**names)
            output = stream.render('xml')
            return dest_path, output
        except (errors.Error,
                genshi.template.TemplateError,
                IOError), error:
            raise errors.VerifyError(source_path, error)
