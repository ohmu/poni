"""
config rendering and verification

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

from path import path
import argh
import argparse
import datetime
import difflib
import itertools
import logging
import re
import sys
import time

from . import colors
from . import errors
from . import template
from . import util


try:
    from argh import expects_obj
except ImportError:
    # older argh version
    expects_obj = lambda m: m


class RenderContext(object):
    """Log information about the template upon rendering errors"""
    def __init__(self, entry, target):
        self.entry = entry
        self.target = target

    def __enter__(self):
        pass

    def __exit__(self, ex_type, ex_value, tb):
        if tb:
            logging.fatal("template render failed: %s: %s: node=%s, config=%s, source=%s, dest=%s, target=%s",
                          ex_type, ex_value,
                          self.entry["node"].name, self.entry["config"].name,
                          self.entry["source_path"], self.entry["dest_path"], self.target)


class Manager:
    def __init__(self, confman):
        self.log = logging.getLogger("manager")
        self.reset()
        self.confman = confman
        self.audit_format = "%8s %s: %s"
        self.frozen = False
        self.files = []
        self.error_count = 0
        self.buckets = {}

    def reset(self):
        self.files = []
        self.error_count = 0
        self.buckets = {}

    def get_bucket(self, name):
        return self.buckets.setdefault(name, freezingset())

    def emit_error(self, node, source_path, error):
        self.log.warning("node %s: %s: %s: %s", node.name, source_path,
                         error.__class__.__name__, error)
        self.error_count += 1

    def copy_tree(self, source_path, dest_path, remote, path_prefix="", verbose=False):
        def progress(copied, total, ctx={}):
            ctx.setdefault("last", time.time())
            if (copied == total) or (time.time() - ctx["last"]) > 1.0:
                sys.stderr.write("\r%s/%s bytes copied" % (copied, total))
                ctx["last"] = time.time()

        dest_dir = path(path_prefix + dest_path)
        try:
            remote.stat(dest_dir)
        except errors.RemoteError:
            remote.makedirs(dest_dir)

        for file_path in path(source_path).files():
            dest_path = dest_dir / file_path.basename()
            lstat = file_path.stat()
            try:
                rstat = remote.stat(dest_path)
                # copy if mtime or size differs
                # TODO: optional full contents comparison
                copy = ((lstat.st_size != rstat.st_size)
                        or (int(lstat.st_mtime) != int(rstat.st_mtime)))
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
               access_method=None, color="auto", config_patterns=None, tag=None):
        self.log.debug("verify: %s", dict(show=show, deploy=deploy,
                                          audit=audit, show_diff=show_diff,
                                          verbose=verbose, callback=callback))
        files = [f for f in self.files if not f.get("report")]
        reports = [f for f in self.files if f.get("report")]
        color = colors.Output(sys.stdout, color=color).color
        stats = util.PropDict(dict(error_count=0, file_count=0))
        config_patterns = [re.compile(p) for p in (config_patterns or [])]
        tag = tag or ""  # empty string indicates untagged files
        for entry in itertools.chain(files, reports):
            if not entry["node"].verify_enabled():
                self.log.debug("filtered: verify disabled: %r", entry)
                continue

            if config_patterns and not any(p.search(entry["config"].name) for p in config_patterns):
                self.log.debug("filtered: config patterns do not match: %r", entry)
                continue

            # is the target excluded from the operation by --tag?
            filtered_out = tag not in (entry.get("tags") or [""])

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
                    continue

                with RenderContext(entry, "source_path"):
                    source_path = entry["config"].plugin.render_name(entry["source_path"])
                with RenderContext(entry, "dest_path"):
                    dest_path = entry["config"].plugin.render_name(entry["dest_path"])
                if deploy:
                    # copy a directory recursively
                    remote = entry["node"].get_remote(override=access_method)
                    self.copy_tree(source_path, dest_path, remote, path_prefix=item_path_prefix,
                                   verbose=verbose)
                else:
                    # verify
                    try:
                        dir_stats = util.dir_stats(source_path)
                    except (OSError, IOError), error:
                        raise errors.VerifyError(
                            "cannot copy files from '%s': %s: %s" % (
                                source_path, error.__class__.__name__, error))

                    if dir_stats["file_count"] == 0:
                        self.log.warning("source directory '%s' is empty" % (
                                source_path))
                    elif verbose:
                        self.log.info(
                            "[OK] copy source directory '%(path)s' has "
                            "%(file_count)s files, "
                            "%(total_bytes)s bytes" % dir_stats)

                # dir handled, next!
                continue

            stats["file_count"] += 1
            source_path = entry["config"].path / entry["source_path"]
            try:
                dest_path = entry["dest_path"]
                if dest_path and dest_path[-1:] == "/":
                    # dest path ending in slash: use source filename
                    dest_path = path(dest_path) / source_path.basename()

                if raw:
                    dest_path, output = dest_path, source_path.bytes()
                else:
                    with RenderContext(entry, "template"):
                        dest_path, output = render(source_path, dest_path, source_text=entry["source_text"])

                if dest_path:
                    dest_path = path(item_path_prefix + dest_path).normpath()

                if (not audit and not deploy) and verbose:
                    # plain verify mode
                    self.log.info("OK: %s: %s", node_name, dest_path)
            except (IOError, errors.Error), error:
                self.emit_error(entry["node"], source_path, error)
                output = util.format_error(error)
                failed = True
                stats["error_count"] += 1

            if output and entry["dest_bucket"]:
                # add the rendered output to the specified bucket
                entry["config"].plugin.add_record(entry["dest_bucket"], text=output)

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

                if dest_path:
                    dest_loc = dest_path
                elif entry.get("dest_bucket"):
                    dest_loc = "bucket:%s" % entry["dest_bucket"]
                else:
                    dest_loc = "(just rendered)"

                identity = "%s%s%s" % (color(node_name, "node"),
                                       color(": path=", "header"),
                                       color(dest_loc, "path"))
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
                except errors.RemoteFileDoesNotExist, error:
                    active_text = None
                    if audit:
                        self.log.error("%s: %s: %s: %s", node_name, dest_path,
                                       error.__class__.__name__, error)
                        stats["error_count"] += 1
                except errors.RemoteError, error:
                    failed = True
                    if audit or deploy:
                        self.log.error("%s: %s: %s: %s", node_name, dest_path,
                                       error.__class__.__name__, error)
                        stats["error_count"] += 1

                    active_text = None
            else:
                active_text = None

            if active_text and audit:
                audit_error = self.audit_output(
                    entry, dest_path, active_text, active_time, output,
                    show_diff=show_diff, color=color,
                    verbose=verbose)

                if audit_error:
                    stats["error_count"] += 1

            if deploy and dest_path and (not failed) and (not filtered_out):
                remote = entry["node"].get_remote(override=access_method)
                try:
                    self.deploy_file(remote, entry, dest_path, output,
                                     active_text, verbose=verbose,
                                     mode=entry.get("mode"),
                                     owner=entry.get("owner"),
                                     group=entry.get("group"))
                except errors.RemoteError, error:
                    stats["error_count"] += 1
                    self.log.error("%s: %s: %s", node_name, dest_path, error)
                    # NOTE: continuing

        if stats["error_count"]:
            raise errors.VerifyError(
                "failed: there were [%(error_count)s/%(file_count)s] errors" % stats)

        return stats

    def deploy_file(self, remote, entry, dest_path, output, active_text,
                    verbose=False, mode=None, owner=None, group=None):
        if output == active_text:
            # nothing to do
            if verbose:
                self.log.info(self.audit_format, "OK",
                              entry["node"].name, dest_path)
        else:
            dest_dir = dest_path.dirname()
            try:
                remote.stat(dest_dir)
            except errors.RemoteError:
                remote.makedirs(dest_dir)

            remote.write_file(dest_path, output, mode=mode, owner=owner,
                              group=group)
            self.log.info(self.audit_format, "WROTE",
                          entry["node"].name, dest_path)

        # post-processing is done always even if file is unchanged
        post_process = entry.get("post_process")
        if post_process:
            # TODO: remote support
            post_process(dest_path)

    def audit_output(self, entry, dest_path, active_text, active_time,
                     output, show_diff=False, color="auto",
                     verbose=False):
        error = False
        if (active_text is not None) and (active_text != output):
            error = True
            self.log.warning(self.audit_format, "DIFFERS",
                             entry["node"].name, dest_path)
            if show_diff:
                color = colors.Output(sys.stdout, color=color).color
                diff = difflib.unified_diff(
                    output.splitlines(True),
                    active_text.splitlines(True),
                    "config", "active",
                    "", active_time,  # TODO: mtime for config?
                    lineterm="\n")

                diff_colors = {"+": "lgreen", "@": "white", "-": "lred"}
                for line in diff:
                    sys.stdout.write(
                        color(line, diff_colors.get(line[:1], "reset")))

                sys.stdout.flush()
        elif active_text and verbose:
            self.log.info(self.audit_format, "OK", entry["node"].name,
                          dest_path)

        return error

    def add_file(self, tags=None, **kw):
        tags = ([tags] if isinstance(tags, basestring) else tags) if tags else []
        kw["tags"] = tags
        self.files.append(kw)


def control(provides=None, requires=None, optional_requires=None, auto_enable=True):
    """decorate a PlugIn method as a 'poni control' command"""
    def wrap(method):
        assert isinstance(provides, (list, tuple, type(None)))
        assert isinstance(requires, (list, tuple, type(None)))
        assert isinstance(optional_requires, (list, tuple, type(None)))
        if auto_enable:
            method.poni_control = dict(provides=provides, requires=requires,
                                       optional_requires=optional_requires)
        else:
            assert not any([provides, requires, optional_requires])

        return expects_obj(method)

    return wrap


class hashabledict(dict):
    def __hash__(self):
        return hash(frozenset(self.iteritems()))


class freezingset(set):
    """set that freezes dicts that are add()ed"""
    def add(self, item):
        assert isinstance(item, dict)
        set.add(self, hashabledict(item))

    def append(self, item):
        """backward-compatibility with old implementation that used lists"""
        self.add(item)


class PlugIn:
    def __init__(self, manager, config, node, top_config):
        self.log = logging.getLogger("plugin")
        self.manager = manager
        self.config = config
        self.top_config = top_config
        self.node = node
        self.controls = {}
        self.render = self.render_cheetah
        self._template_cache = {}
        self._template_cache_reset_counter = 0

    def add_actions(self):
        pass

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

        rendered_path = self.render_name(script_path)
        remote = arg.node.get_remote(override=arg.method)
        lines = [] if yield_stdout else None
        color = colors.Output(sys.stdout, color=arg.color).color
        exit_code = remote.execute(rendered_path, verbose=arg.verbose,
                                   output_lines=lines, quiet=arg.quiet,
                                   output_file=arg.output_file,
                                   color=color)
        if exit_code:
            raise errors.ControlError("%r failed with exit code %r" % (
                    rendered_path, exit_code))

        for line in (lines or []):
            yield line

    def add_argh_control(self, handler, provides=None, requires=None,
                         optional_requires=None):
        try:
            name = handler.argh_alias
        except AttributeError:
            name = handler.__name__

        def handle_control(control_name, args, **kwargs):
            return self.handle_argh_control(handler, control_name, args,
                                            **kwargs)

        name = name.replace("_", "-")
        self.controls[name] = dict(
            callback=handle_control,
            config=self.config,
            node=self.node,
            optional_requires=optional_requires or [],
            plugin=self,
            provides=provides or [],
            requires=requires or [],
            )

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
                            quiet=False, output_dir=None, color="auto",
                            method=None, send_output=None, node=None):
        assert node
        parser = argh.ArghParser(prog="control")
        parser.add_commands([handler])
        full_args = [control_name] + args
        namespace = argparse.Namespace()
        namespace.verbose = verbose
        namespace.quiet = quiet
        namespace.method = method
        namespace.send_output = send_output
        namespace.node = node
        namespace.color = color
        if output_dir:
            output_file_path = output_dir / ("%s.log" % node.name.replace("/", "_"))
            namespace.output_file = file(output_file_path, "at")
        else:
            namespace.output_file = None

        parser.dispatch(argv=full_args, namespace=namespace)

    def get_override_config_path(self, filename):
        for search_path in (self.top_config.path, self.config.path):
            file_path = search_path / filename
            if file_path.exists():
                return file_path.abspath()
        raise errors.VerifyError("no %r found for config %r" % (
                filename, self.top_config.name))

    def add_file(self, source_path, dest_path=None, source_text=None,
                 dest_bucket=None, owner=None, group=None,
                 render=None, report=False, post_process=None, mode=None,
                 auto_override=False, tags=None):
        render = render or self.render
        if auto_override:
            source_path = self.get_override_config_path(source_path)
        return self.manager.add_file(node=self.node, config=self.config,
                                     type="file", dest_path=dest_path,
                                     source_path=source_path,
                                     source_text=source_text,
                                     render=render, report=report,
                                     post_process=post_process,
                                     dest_bucket=dest_bucket,
                                     owner=owner, group=group,
                                     mode=mode, tags=tags)

    def add_dir(self, source_path, dest_path, render=None, tags=None):
        render = render or self.render
        return self.manager.add_file(type="dir", node=self.node,
                                     config=self.config, dest_path=dest_path,
                                     source_path=source_path, render=render,
                                     tag=tags)

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

    def render_text(self, source_path, dest_path, source_text=None):
        try:
            # paths are always rendered as templates
            dest_path = self.render_name(dest_path)
            text = source_text if (source_text is not None) else file(source_path, "rb").read()
            return dest_path, text
        except (IOError, OSError), error:
            raise errors.VerifyError(source_path, error)

    def add_edge(self, bucket_name, dest_node, dest_config, **kwargs):
        self.add_record(bucket_name, dest_node=dest_node, dest_config=dest_config,
                        **kwargs)

    def add_record(self, bucket_name, **kwargs):
        self.manager.get_bucket(bucket_name).add(
            hashabledict(source_node=self.node, source_config=self.top_config,
                 **kwargs))

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
                     record=self.add_record,
                     plugin=self)
        return names

    def cached_template(self, key, renderer):
        if self.manager.confman._cache_reset_counter != self._template_cache_reset_counter:
            # conf manager cache has been reset, we need to invalidate our internal cache, too
            self._template_cache = {}
            self._template_cache_reset_counter = self.manager.confman._cache_reset_counter

        # see if the template has already been rendered and is in cache
        cached = self._template_cache.get(key)
        if cached:
            return cached

        rendered = renderer()
        self._template_cache[key] = rendered  # cache result for next time
        return rendered

    def render_name(self, name, names=None):
        if not name or (("$" not in name) and ("#" not in name)):
            return name  # skip rendering in trivial cases

        return self.cached_template(("name", hash(name)),
                                    lambda: template.render_name(name, None, names or self.get_names()))

    def render_cheetah(self, source_path, dest_path, source_text=None):
        if source_text and ("$" not in source_text) and ("#" not in source_text):
            return (self.render_name(dest_path), source_text)  # skip rendering in trivial cases
        else:
            return (self.render_name(dest_path),
                    self.cached_template(("cheetah", hash(source_text), source_path),
                                         lambda: self._render(template.render_cheetah, source_text, source_path)))

    def render_mako(self, source_path, dest_path, source_text=None):
        return (self.render_name(dest_path),
                self.cached_template(("mako", hash(source_text), source_path),
                                     lambda: self._render(template.render_mako, source_text, source_path)))

    def render_genshi_xml(self, source_path, dest_path, source_text=None):
        return (self.render_name(dest_path),
                self.cached_template(("genshi", hash(source_text), source_path),
                                     lambda: self._render(template.render_genshi, source_text, source_path)))

    def _render(self, renderer, source_text, source_path):
        names = self.get_names()
        if source_text:
            source_path = None
        elif source_path:
            source_path = self.render_name(source_path, names=names)

        return renderer(source_text, source_path, names)
