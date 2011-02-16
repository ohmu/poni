"""
core logic

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

import re
import sys
import imp
import shutil
from path import path
from .util import json
from . import newconfig
from . import errors
from . import util
from . import rcontrol_all
from . import vc

NODE_CONF_FILE = "node.json"
SYSTEM_CONF_FILE = "system.json"
CONFIG_CONF_FILE = "config.json"
REPO_CONF_FILE = "repo.json"
CONFIG_DIR = "config"
PLUGIN_FILE = "plugin.py"
SETTINGS_DIR = "settings"

DONT_SHOW = set(["cloud"])
DONT_SAVE = set(["index", "sub_count", "depth"])


def ensure_dir(typename, root, name, must_exist):
    """validate dir 'name' under 'root': dir either 'must_exist' or not"""
    target_dir = path(root) / name
    exists = target_dir.exists()
    if (not must_exist) and exists:
        raise errors.UserError("%s %r already exists" % (typename, name))
    elif must_exist and (not exists):
        raise errors.UserError("%s %r does not exist" % (typename, name))

    return target_dir


class ConfigMatch:
    def __init__(self, pattern, full_match=False):
        if "$" in pattern[:-1]:
            # make sure no unexpanded macros leak from templates
            raise errors.UserError("invalid chars in pattern %r" % pattern)

        pattern = pattern.replace("//", "/.*/")
        parts = pattern.rsplit("/", 1)
        if len(parts) == 2:
            node_pattern, config_pattern = parts
        else:
            node_pattern = "."
            config_pattern = parts[0]

        if full_match:
            if not config_pattern.endswith("$"):
                config_pattern += "$"

            self.match_config = re.compile(config_pattern).match

            if not node_pattern.endswith("$"):
                node_pattern += "$"

            self.match_node = re.compile(node_pattern).match

        else:
            self.match_config = re.compile(config_pattern).search
            self.match_node = re.compile(node_pattern).search

    def matches(self, node, conf):
        if not self.match_node(node.name):
            return False

        return self.match_config(conf.name)


class Item(dict):
    """Generic tree item type"""
    def __init__(self, typename, system, name, item_dir, conf_file, extra):
        dict.__init__(self)
        assert isinstance(system, (System, type(None)))
        assert isinstance(typename, (str, unicode))
        assert isinstance(name, (str, unicode))
        assert isinstance(item_dir, path)
        assert isinstance(extra, (dict, type(None)))
        self.type = typename
        self.system = system
        self.name = name
        self.path = item_dir
        self.conf_file = conf_file
        self.update(extra or {})

    def showable(self):
        """Yields (key, value) for all items visible by default"""
        for k, v in sorted(self.iteritems()):
            if k not in DONT_SHOW:
                yield k, v

    def set_properties(self, props):
        """
        Set a bunch of item properties. Handles multi-level props suchs
        as 'foo.bar.baz'.

        Returns list of changes made: [(item_key, old_value, new_value)]
        """
        changes = []
        for key_str, value in props.iteritems():
            old_value = util.set_dict_prop(self, key_str.split("."), value)
            changes.append((key_str, old_value, value))

        return changes

    def log_update(self, updates):
        """
        Update properties from dict 'updates'.

        Returns a list of changes made: [(prop_name, old_value, new_value)]
        """
        changes = []
        for key, value in updates.iteritems():
            old = self.get(key)
            if old != value:
                self[key] = value
                changes.append((key, old, value))

        return changes

    def saveable(self):
        """Yields (key, value) for all properties that should be saved"""
        for k, v in sorted(self.iteritems()):
            if k not in DONT_SAVE:
                yield k, v

    def verify_enabled(self):
        """Is verification (including deploy and audit) enabled for item?"""
        return (self.get_tree_property("verify", True)
                and not self.get_tree_property("template", False))

    def get_tree_property(self, name, default=None):
        """Return property value from the closest ancestor (including self)"""
        value = self.get(name)
        if value is not None:
            return value

        if self.system:
            return self.system.get_tree_property(name, default=default)

        return default

    def __str__(self):
        return ", ".join(("%s=%r" % item) for item in self.showable())

    def save(self):
        """Save item properties to persistent storage"""
        util.json_dump(dict(self.saveable()), self.conf_file)

    def cleanup(self):
        pass


class Config(Item):
    def __init__(self, node, name, config_dir, extra=None):
        Item.__init__(self, "config", None, name, config_dir,
                      config_dir / CONFIG_CONF_FILE, extra)
        self.update(json.load(file(self.conf_file)))
        self.node = node
        self.settings_dir = self.path / SETTINGS_DIR
        # TODO: lazy-load settings
        self.settings = newconfig.Config(self.get_settings_dirs())
        self.controls = None
        self.plugin = None

    def get_plugin(self):
        if self.plugin:
            return self.plugin

        parent_config_name = self.get("parent")
        if not parent_config_name:
            return None

        parent_conf_node, parent_config = self.node.confman.get_config(
            parent_config_name)

        return parent_config.get_plugin()

    def load_settings_layer(self, file_name):
        try:
            return json.load((self.settings_dir / file_name).open())
        except (IOError, OSError):
            return {}

    def save_settings_layer(self, file_name, layer):
        if not self.settings_dir.exists():
            self.settings_dir.mkdir()

        full_path = self.settings_dir / file_name
        util.json_dump(layer, full_path)
        self.settings.reload()

    def get_settings_dirs(self):
        parent_config_name = self.get("parent")
        if parent_config_name:
            # TODO: find_config() that returns exactly one hit
            hits = list(self.node.confman.find_config(parent_config_name,
                                                      full_match=True))
            if len(hits) == 1:
                parent_config_node, parent_config = hits[0]
                for item in parent_config.get_settings_dirs():
                    yield item
            else:
                raise errors.Error("need exactly one parent config %r" % (
                        parent_config_name))

        yield "%s/%s" % (self.node.name, self.name), self.settings_dir

    def saveable(self):
        return self.iteritems()

    def showable(self):
        dont_show = set(["node", "name", "path", "settings_dir", "conf"])
        for k, v in sorted(self.iteritems()):
            if k not in dont_show:
                yield k, v

    def collect(self, manager, node, top_config=None):
        top_config = top_config or self
        plugin_path = self.path / PLUGIN_FILE
        if not plugin_path.exists():
            # no plugin, nothing to verify
            return

        module = imp.load_source("plugin", plugin_path)
        plugin = module.PlugIn(manager, self, node, top_config)
        plugin.add_actions()
        plugin.add_all_controls()
        top_config.plugin = plugin # TODO

    def collect_parents(self, manager, node, top_config=None):
        top_config = top_config or self
        parent_name = self.get("parent")
        if not parent_name:
            return

        matches = list(self.node.confman.find_config(parent_name,
                                                     full_match=True))
        if len(matches) == 0:
            raise errors.Error("config '%s/%s' parent config %r not found" % (
                    self.node.name, self.name, parent_name))
        elif len(matches) > 1:
            names = (("%s/%s" % (c.node.name, c.name)) for pn, c in matches)
            raise errors.Error("config %s/%s's parent config %r matches "
                               "multiple configs: %s" % (
                    self.node.name, self.name, parent_name, ", ".join(names)))

        parent_conf_node, parent_conf = matches[0]
        parent_conf.collect(manager, node, top_config=top_config)
        # TODO: parent_conf.collect_parents() (multiple levels of parents)


class Node(Item):
    def __init__(self, confman, system, name, item_dir, extra=None):
        Item.__init__(self, "node", system, name, item_dir,
                      item_dir / NODE_CONF_FILE, extra)
        self.confman = confman
        self._remotes = {}
        self.config_cache = {}
        self.update(json.load(file(self.conf_file)))

    def cleanup(self):
        for remote in self._remotes.values():
            remote.close()

    def get_remote(self, override=None):
        method = override or self.get_tree_property("deploy", None)
        remote = self._remotes.get(method)
        if not remote:
            remote = rcontrol_all.get_remote(self, method)
            self._remotes[method] = remote

        return remote

    def add_config(self, config, parent=None, copy_dir=None):
        config_dir = self.path / CONFIG_DIR / config
        if config_dir.exists():
            raise errors.UserError(
                "%s: config %r already exists" % (self.name, config))

        if copy_dir:
            try:
                shutil.copytree(copy_dir, config_dir, symlinks=True)
            except (IOError, OSError), error:
                raise errors.Error("copying config files failed: %s: %s" % (
                        error.__class__.__name__, error))
        else:
            config_dir.makedirs()

        conf_file = config_dir / CONFIG_CONF_FILE
        conf = {}
        if parent:
            conf["parent"] = parent

        util.json_dump(conf, conf_file)

        settings_dir = config_dir / SETTINGS_DIR
        if not settings_dir.exists():
            settings_dir.mkdir() # pre-created so it is there for copying files

    def iter_configs(self):
        config_dir = self.path / CONFIG_DIR
        if config_dir.exists():
            for config_path in config_dir.dirs():
                conf = self.config_cache.get(config_path)
                if conf is None:
                    conf = Config(self, config_path.basename(), config_path)
                    self.config_cache[config_path] = conf

                yield conf

    def iter_all_configs(self, handled=None):
        handled = handled or set()
        for conf in self.iter_configs():
            if conf.name not in handled:
                handled.add(conf.name)
                yield conf

        parent_name = self.get("parent")
        if parent_name:
            # collect configs from parent node
            parent_path = self.confman.system_root / parent_name
            parent_node = self.confman.get_node(parent_path, self.system)
            for conf in parent_node.iter_all_configs(handled=handled):
                yield conf

    def collect(self, manager):
        for conf in self.iter_configs():
            conf.collect(manager, self)

    def collect_parents(self, manager, node=None):
        node = node or self
        parent_name = self.get("parent")
        if parent_name:
            # collect configs from parent node
            parent_path = self.confman.system_root / parent_name
            parent_node = self.confman.get_node(parent_path, self.system)
            for conf in parent_node.iter_configs():
                conf.collect(manager, node)

            # collect parent's parents ad infinitum...
            parent_node.collect_parents(manager, node)

        # collect configs from this node's inherited configs
        for conf in self.iter_configs():
            conf.collect_parents(manager, node)


class System(Item):
    def __init__(self, system, name, system_path, sub_count, extra=None):
        Item.__init__(self, "system", system, name, system_path,
                      system_path / SYSTEM_CONF_FILE, extra)
        self["sub_count"] = sub_count
        try:
            self.update(json.load(file(self.conf_file)))
        except IOError:
            pass


class ConfigMan:
    def __init__(self, root_dir, must_exist=True):
        # TODO: check repo.json from dir, option to start verification
        self.root_dir = path(root_dir)
        self.system_root = self.root_dir / "system"
        self.config_path = self.root_dir / REPO_CONF_FILE
        self.node_cache = {}
        if must_exist:
            conf = self.load_config()
            self.apply_library_paths(conf.get("libpath", {}))

        self.vc = vc.create_vc(self.root_dir)

    def apply_library_paths(self, path_dict):
        """add repo's custom library include paths to sys.path"""
        for lib_path in path_dict.values():
            lib_path = path(lib_path)
            if not lib_path.isabs():
                lib_path = self.root_dir / lib_path

            sys.path.append(lib_path)

    def init_repo(self):
        if self.config_path.exists():
            raise errors.Error("repository '%s' already initialized" % (
                    self.root_dir))

        try:
            if not self.system_root.exists():
                self.system_root.makedirs()

            util.json_dump({}, self.config_path)
        except (OSError, IOError), error:
            raise errors.RepoError("repository '%s' init failed: %s: %s" % (
                    self.root_dir, error.__class__.__name__, error))

    def set_library_path(self, name, lib_path):
        conf = self.load_config()
        libpath = conf.setdefault("libpath", {})
        libpath[name] = lib_path
        self.save_config(conf)

    def load_config(self):
        try:
            return json.load(file(self.config_path))
        except Exception, error:
            raise errors.RepoError(
                "%s: not a valid repo (hint: 'init'-command): %s: %s" % (
                    self.root_dir, error.__class__.__name__, error))

    def save_config(self, conf):
        util.json_dump(conf, self.config_path)

    def cleanup(self):
        for node in self.node_cache.itervalues():
            node.cleanup()

    def get_system_dir(self, name, must_exist=True):
        return ensure_dir("system", self.system_root, name, must_exist)

    def get_node_dir(self, system, name, must_exist=True):
        return ensure_dir("node", self.get_system_dir(system), name,
                          must_exist)

    def create_system(self, name):
        system_dir = self.get_system_dir(name, must_exist=False)
        system_dir.makedirs()
        spec_file = system_dir / SYSTEM_CONF_FILE
        util.json_dump({}, spec_file)
        return system_dir

    def system_exists(self, name):
        return (path(self.system_root) / name).exists()

    def create_node(self, node, host=None, parent_node_name=None,
                    copy_props=None):
        system_dir, node_name = path(node).splitpath()
        if not self.system_exists(system_dir):
            self.create_system(system_dir)

        node_dir = self.get_node_dir(system_dir, node_name, must_exist=False)
        node_dir.makedirs()
        spec_file = node_dir / NODE_CONF_FILE

        if copy_props and parent_node_name:
            parent_node_conf = (self.system_root / parent_node_name
                                / NODE_CONF_FILE)
            spec = json.load(file(parent_node_conf))
        else:
            spec = {}

        spec["host"] = host or ""
        if parent_node_name:
            spec["parent"] = parent_node_name

        util.json_dump(spec, spec_file)

    def get_node(self, node_path, system, extra=None, name=None):
        # TODO: random calls to this before loading ALL nodes will result
        # in missing 'extra' info
        extra = extra or {}
        node = self.node_cache.get(node_path)
        if not node:
            name = name or node_path[len(self.system_root)+1:]
            node = Node(self, system, name, node_path, extra=extra)
            self.node_cache[node_path] = node

        return node

    def get_config(self, pattern):
        configs = list(self.find_config(pattern, all_configs=True,
                                        full_match=True))
        if len(configs) == 0:
            raise errors.Error("no config %r found" % (pattern))
        elif len(configs) > 1:
            raise errors.Error("found multiple %r configs: %s" % (
                    pattern, ", ".join(("%s/%s" % (c.node.name, c.name))
                                       for cn, c in configs)))

        return configs[0]

    def find_config(self, pattern, all_configs=False, full_match=False):
        comparison = ConfigMatch(pattern, full_match=full_match)
        for node in self.find("."):
            if not comparison.match_node(node.name):
                continue

            if all_configs:
                find_method = node.iter_all_configs
            else:
                find_method = node.iter_configs

            for conf in find_method():
                if comparison.match_config(conf.name):
                    yield node, conf

    def find(self, pattern, current=None, system=None, nodes=True,
             systems=False, curr_depth=0, extra=None, depth=None,
             full_match=False):
        depth = depth or []
        extra = extra or {}
        pattern = pattern or ""

        if isinstance(pattern, (str, unicode)):
            if full_match and not pattern.endswith("$"):
                pattern += "$"

            pattern = re.compile(pattern or "")

        match_op = pattern.match if full_match else pattern.search
        current = current or self.system_root
        node_conf_file = current / NODE_CONF_FILE
        name = current[len(self.system_root)+1:]
        ok_depth = (not depth) or (curr_depth in depth)

        if node_conf_file.exists():
            # this is a node dir
            if nodes and match_op(name) and ok_depth:
                yield self.get_node(current, system, extra=extra)
        else:
            # system dir
            subdirs = current.dirs()
            subdirs.sort()
            system = System(system, name, current, len(subdirs), extra=extra)
            if (systems and (current != self.system_root) and ok_depth
                and match_op(name)):
                yield system

            for sub_index, subdir in enumerate(subdirs):
                sub_depth = curr_depth + 1
                extra = dict(index=sub_index, depth=sub_depth)

                for result in self.find(pattern, current=subdir, system=system,
                                        nodes=nodes, systems=systems,
                                        curr_depth=sub_depth, extra=extra,
                                        depth=depth, full_match=full_match):
                    yield result
