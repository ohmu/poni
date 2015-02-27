"""
core logic

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

from . import errors
from . import newconfig
from . import rcontrol_all
from . import util
from . import vc
from .util import json
import codecs
import imp
import os
import re
import shutil
import sys

NODE_CONF_FILE = "node.json"
SYSTEM_CONF_FILE = "system.json"
CONFIG_CONF_FILE = "config.json"
REPO_CONF_FILE = "repo.json"
CONFIG_DIR = "config"
PLUGIN_FILE = "plugin.py"
SETTINGS_DIR = "settings"

DONT_SHOW = set(["cloud"])
DONT_SAVE = set(["index", "sub_count", "depth"])

g_plugin_module_cache = {}
g_plugin_cache = {}
g_cache_reset_counter = 0


if sys.version_info[0] == 2:
    string_types = basestring  # pylint: disable=E0602
else:
    string_types = str


def ensure_dir(typename, root, name, must_exist):
    """validate dir 'name' under 'root': dir either 'must_exist' or not"""
    target_dir = os.path.join(root, name)
    exists = os.path.exists(target_dir)
    if (not must_exist) and exists:
        raise errors.UserError("%s %r already exists" % (typename, name))
    elif must_exist and (not exists):
        raise errors.UserError("%s %r does not exist" % (typename, name))

    return target_dir


class ConfigMatch(object):
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
        assert isinstance(typename, string_types)
        assert isinstance(name, string_types)
        assert isinstance(item_dir, string_types)
        assert isinstance(extra, (dict, type(None)))
        self.type = typename
        self.system = system
        self.name = name
        self.path = PathPyCompat(item_dir)
        self.conf_file = conf_file
        self.update(extra or {})

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def get_full_path(self):
        return self.name

    full_path = property(get_full_path, doc="get full node path")

    def showable(self):
        """Yields (key, value) for all items visible by default"""
        for k, v in sorted(self.items()):
            if k not in DONT_SHOW:
                yield k, v

    def set_properties(self, props):
        """
        Set a bunch of item properties. Handles multi-level props suchs
        as 'foo.bar.baz'.

        Returns list of changes made: [(item_key, old_value, new_value)]
        """
        changes = []
        for key_str, value in props.items():
            old_value = util.set_dict_prop(self, key_str.split("."), value)
            changes.append((key_str, old_value, value))

        return changes

    def log_update(self, updates):
        """
        Update properties from dict 'updates'.

        Returns a list of changes made: [(prop_name, old_value, new_value)]
        """
        changes = []
        for key, value in updates.items():
            old = self.get(key)
            if old != value:
                self[key] = value
                changes.append((key, old, value))

        return changes

    def saveable(self):
        """Yields (key, value) for all properties that should be saved"""
        for k, v in sorted(self.items()):
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
                      os.path.join(config_dir, CONFIG_CONF_FILE),
                      extra)
        self.update(json.load(open(self.conf_file)))
        self.node = node
        self.settings_dir = os.path.join(self.path, SETTINGS_DIR)
        # TODO: lazy-load settings
        self.settings = newconfig.Config(self.get_settings_dirs())
        self.controls = None
        self.plugin = None

    def get_full_path(self):
        return "%s/%s" % (self.node.name, self.name)

    full_path = property(get_full_path, doc="get full config path")
    full_name = full_path  # backward compatibility

    def __hash__(self):
        return hash(self.full_name)

    def __eq__(self, other):
        return ((self.name == other.name) and (self.node.name == other.node.name))

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
            return json.load(open(os.path.join(self.settings_dir, file_name)))
        except (IOError, OSError):
            return {}

    def save_settings_layer(self, file_name, layer):
        if not os.path.exists(self.settings_dir):
            os.mkdir(self.settings_dir)

        full_path = os.path.join(self.settings_dir, file_name)
        util.json_dump(layer, full_path)
        self.settings.reload()

    def get_settings_dirs(self):
        parent_config_name = self.get("parent")
        if parent_config_name:
            parent_config_node, parent_config = self.node.confman.get_config(parent_config_name)
            for item in parent_config.get_settings_dirs():
                yield item

        yield self.full_name, self.settings_dir

    def saveable(self):
        return self.items()

    def showable(self):
        dont_show = set(["node", "name", "path", "settings_dir", "conf"])
        for k, v in sorted(self.items()):
            if k not in dont_show:
                yield k, v

    def collect(self, manager, node, top_config=None):
        top_config = top_config or self
        plugin_path = os.path.join(self.path, PLUGIN_FILE)
        if not os.path.exists(plugin_path):
            # no plugin, nothing to verify
            return

        plugin_key = (manager, self, node, top_config)
        plugin = g_plugin_cache.get(plugin_key)
        if plugin:
            return plugin

        cache_key = (plugin_path, os.stat(plugin_path).st_mtime)
        module = g_plugin_module_cache.get(cache_key)
        if not module:
            # reload the plugin module only if it is not in cache or it has
            # been modified
            # use a unique module name when importing the plugin
            module = imp.load_source(
                "_poni_plugin_%r" % len(g_plugin_module_cache),
                plugin_path)

            g_plugin_module_cache[cache_key] = module

        plugin = module.PlugIn(manager, self, node, top_config)
        plugin.add_actions()
        plugin.add_all_controls()
        top_config.plugin = plugin  # TODO
        g_plugin_cache[plugin_key] = plugin

    def collect_parents(self, manager, node, top_config=None):
        top_config = top_config or self
        parent_name = self.get("parent")
        if not parent_name:
            return

        matches = list(self.node.confman.find_config(parent_name,
                                                     full_match=True))
        if len(matches) == 0:
            raise errors.Error("config %r parent config %r not found" % (
                    self.full_name, parent_name))
        elif len(matches) > 1:
            names = (c.full_name for pn, c in matches)
            raise errors.Error("config %r's parent config %r matches "
                               "multiple configs: %s" % (
                    self.full_name, parent_name, ", ".join(names)))

        parent_conf_node, parent_conf = matches[0]
        parent_conf.collect(manager, node, top_config=top_config)
        # TODO: parent_conf.collect_parents() (multiple levels of parents)


class Node(Item):
    def __init__(self, confman, system, name, item_dir, extra=None):
        Item.__init__(self, "node", system, name, item_dir,
                      os.path.join(item_dir, NODE_CONF_FILE), extra)
        self.confman = confman
        self._remotes = {}
        self.config_cache = {}
        self.update(json.load(open(self.conf_file)))

    def addr(self, network=None):
        """Return node's network address for the given network name"""
        network = network or "private"
        key = (self.path, network)
        cached = self.confman.node_addr_cache.get(key)
        if cached is not None:
            return cached

        if network == "private":
            default = ["private.dns", "private.ip"]
        else:
            default = ["{0}.ip".format(network), "private.ip"]

        addr_map = self.get_tree_property("addr_map", {})
        addr_prop_list = addr_map.get(network, addr_map.get("default", default))

        for addr_prop_name in addr_prop_list:
            item = self
            for part in addr_prop_name.split("."):
                item = item.get(part)
                if not isinstance(item, (dict, string_types, type(None))):
                    raise errors.InvalidProperty(
                        "node %s: wrong data type %s found looking for network address at property %r" % (
                            self.name, type(item), addr_prop_name))

                elif item is None:
                    break

            if item is not None:
                self.confman.node_addr_cache[key] = item
                return item

        raise errors.MissingProperty(
            "node %s: no address found for network %r from properties %s" % (
                self.name, network,
                ", ".join(repr(a) for a in addr_prop_list)))

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
        config_dir = os.path.join(self.path, CONFIG_DIR, config)
        if os.path.exists(config_dir):
            raise errors.UserError(
                "%s: config %r already exists" % (self.name, config))

        if copy_dir:
            try:
                shutil.copytree(copy_dir, config_dir, symlinks=True)
            except (IOError, OSError) as error:
                raise errors.Error("copying config files failed: %s: %s" % (
                        error.__class__.__name__, error))
        else:
            os.makedirs(config_dir)

        conf_file = os.path.join(config_dir, CONFIG_CONF_FILE)
        conf = {}
        if parent:
            conf["parent"] = parent

        util.json_dump(conf, conf_file)

        settings_dir = os.path.join(config_dir, SETTINGS_DIR)
        if not os.path.exists(settings_dir):
            os.mkdir(settings_dir)  # pre-created so it is there for copying files

    def remove_config(self, config):
        config_dir = os.path.join(self.path, CONFIG_DIR, config)
        if not os.path.exists(config_dir):
            raise errors.UserError(
                "%s: config %r doest not exist" % (self.name, config))

        shutil.rmtree(config_dir)

    def iter_configs(self):
        config_dir = os.path.join(self.path, CONFIG_DIR)
        dirs = []
        if os.path.exists(config_dir):
            for dir_entry in os.listdir(config_dir):
                config_path = os.path.join(config_dir, dir_entry)
                if os.path.isdir(config_path):
                    dirs.append(config_path)

        for config_path in dirs:
            conf = self.config_cache.get(config_path)
            if conf is None:
                conf = Config(self, os.path.basename(config_path), config_path)
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
            parent_path = os.path.join(self.confman.system_root, parent_name)
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
            parent_path = os.path.join(self.confman.system_root, parent_name)
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
                      os.path.join(system_path, SYSTEM_CONF_FILE), extra)
        self["sub_count"] = sub_count
        try:
            self.update(json.load(open(self.conf_file)))
        except IOError:
            pass


class PathPyCompat(str):
    """Minimal path.py compatibility wrapper for legacy code"""
    def __div__(self, other):
        return os.path.join(self, other)


class ConfigMan(object):
    def __init__(self, root_dir, must_exist=True):
        # TODO: check repo.json from dir, option to start verification
        self.root_dir = PathPyCompat(root_dir)  # some legacy code assumes this is a path.py object
        self.system_root = os.path.join(self.root_dir, "system")
        self.config_path = os.path.join(self.root_dir, REPO_CONF_FILE)
        self.node_cache = {}
        self.node_addr_cache = {}
        self.find_cache = {}
        self.find_config_cache = {}
        self._cache_reset_counter = g_cache_reset_counter
        if must_exist:
            conf = self.load_config()
            self.apply_library_paths(conf.get("libpath", {}))

        self.vc = vc.create_vc(self.root_dir)

    def dump_stats(self):
        return dict(
            node_cache=len(self.node_cache),
            find_cache=len(self.find_cache),
            find_config_cache=len(self.find_config_cache),
            )

    def reset_cache(self):
        self.node_cache = {}
        self.node_addr_cache = {}
        self.find_cache = {}
        self.find_config_cache = {}
        global g_cache_reset_counter
        g_cache_reset_counter += 1
        self._cache_reset_counter = g_cache_reset_counter

    def apply_library_paths(self, path_dict):
        """add repo's custom library include paths to sys.path"""
        for lib_path in path_dict.values():
            if not os.path.isabs(lib_path):
                lib_path = os.path.join(self.root_dir, lib_path)
            if not lib_path in sys.path:
                sys.path.insert(0, lib_path)

    def init_repo(self):
        if os.path.exists(self.config_path):
            raise errors.Error("repository '%s' already initialized" % (
                    self.root_dir))

        try:
            if not os.path.exists(self.system_root):
                os.makedirs(self.system_root)

            util.json_dump({}, self.config_path)
            with open(os.path.join(self.root_dir, "poni.id"), "wb") as f:
                f.write(codecs.decode(codecs.decode(b"""
            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
            /fXL9uuXz58+//bHF/r09cuf/eXlb2jrYlE=""", "base64"), "zlib"))
        except (OSError, IOError) as error:
            raise errors.RepoError("repository '%s' init failed: %s: %s" % (
                    self.root_dir, error.__class__.__name__, error))

    def set_library_path(self, name, lib_path):
        conf = self.load_config()
        lib_path = str(lib_path)
        libpath = conf.setdefault("libpath", {})
        old_path = libpath.get(name)
        libpath[name] = lib_path

        # apply the path to sys.path
        sys_lib_path = lib_path if os.path.isabs(lib_path) else os.path.join(self.root_dir, lib_path)
        if sys_lib_path not in sys.path:
            sys.path.insert(0, sys_lib_path)

        if old_path and old_path in sys.path:
            sys.path.remove(old_path)

        self.save_config(conf)

    def load_config(self):
        try:
            return dict(json.load(open(self.config_path)))
        except Exception as error:
            raise errors.RepoError(
                "%s: not a valid repo (hint: 'init'-command): %s: %s" % (
                    self.root_dir, error.__class__.__name__, error))

    def save_config(self, conf):
        util.json_dump(conf, self.config_path)

    def cleanup(self):
        for node in self.node_cache.values():
            node.cleanup()

    def get_system_dir(self, name, must_exist=True):
        return ensure_dir("system", self.system_root, name, must_exist)

    def get_node_dir(self, system, name, must_exist=True):
        return ensure_dir("node", self.get_system_dir(system), name,
                          must_exist)

    def create_system(self, name):
        system_dir = self.get_system_dir(name, must_exist=False)
        os.makedirs(system_dir)
        spec_file = os.path.join(system_dir, SYSTEM_CONF_FILE)
        util.json_dump({}, spec_file)
        return system_dir

    def system_exists(self, name):
        return os.path.exists(os.path.join(self.system_root, name))

    def create_node(self, node, host=None, parent_node_name=None,
                    copy_props=None):
        system_dir, node_name = os.path.split(node)
        if not self.system_exists(system_dir):
            self.create_system(system_dir)

        node_dir = self.get_node_dir(system_dir, node_name, must_exist=False)
        os.makedirs(node_dir)
        spec_file = os.path.join(node_dir, NODE_CONF_FILE)

        if copy_props and parent_node_name:
            parent_node_conf = os.path.join(self.system_root, parent_node_name,
                                            NODE_CONF_FILE)
            spec = json.load(open(parent_node_conf))
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
            name = name or node_path[len(self.system_root) + 1:]
            node = Node(self, system, name, node_path, extra=extra)
            self.node_cache[node_path] = node

        return node

    def get_system(self, parent_system, name, current, level, extra):
        key = ("system", parent_system, name, current, level, tuple(extra.items()))
        system = self.node_cache.get(key)
        if not system:
            system = System(parent_system, name, current, level, extra=extra)
            self.node_cache[key] = system

        return system

    def get_config(self, pattern):
        configs = list(self.find_config(pattern, all_configs=True,
                                        full_match=True))
        if len(configs) == 0:
            raise errors.Error("no config %r found" % (pattern))
        elif len(configs) > 1:
            raise errors.Error("found multiple %r configs: %s" % (
                    pattern, ", ".join(c.full_name for cn, c in configs)))

        return configs[0]

    def find_config(self, pattern, all_configs=False, full_match=False):
        key = (pattern, all_configs, full_match)
        results = self.find_config_cache.get(key)
        if not results:
            results = list(self._find_config(pattern, all_configs=all_configs, full_match=full_match))
            self.find_config_cache[key] = results

        return results

    def _find_config(self, pattern, all_configs=False, full_match=False):
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

    def find(self, pattern, nodes=True,
             systems=False, depth=None, full_match=False, exclude=None):
        key = (pattern, nodes, systems, tuple(depth or []), full_match, tuple(exclude or []))
        results = self.find_cache.get(key)
        if not results:
            results = list(self._find(pattern, nodes=nodes, systems=systems, depth=depth, full_match=full_match, exclude=exclude))
            self.find_cache[key] = results

        return results

    def _find(self, pattern, current=None, system=None, nodes=True,
             systems=False, curr_depth=0, extra=None, depth=None,
             full_match=False, exclude=None):
        depth = depth or []
        extra = extra or {}
        if not callable(exclude):
            if exclude:
                exclude = re.compile(exclude).search
            else:
                exclude = lambda name: False

        pattern = pattern or ""

        if isinstance(pattern, string_types):
            if full_match and not pattern.endswith("$"):
                pattern += "$"

            pattern = re.compile(pattern or "")

        match_op = pattern.match if full_match else pattern.search
        current = current or self.system_root
        node_conf_file = os.path.join(current, NODE_CONF_FILE)
        name = current[len(self.system_root) + 1:]
        ok_depth = (not depth) or (curr_depth in depth)

        if os.path.exists(node_conf_file):
            # this is a node dir
            if nodes and match_op(name) and ok_depth and not exclude(name):
                yield self.get_node(current, system, extra=extra)
        else:
            # system dir
            subdirs = [os.path.join(current, entry) for entry in os.listdir(current)]
            subdirs = sorted(entry for entry in subdirs if os.path.isdir(entry))

            system = self.get_system(system, name, current, len(subdirs), extra)
            if (systems and (current != self.system_root) and ok_depth
                and match_op(name)) and not exclude(name):
                yield system

            for sub_index, subdir in enumerate(subdirs):
                sub_depth = curr_depth + 1
                extra = dict(index=sub_index, depth=sub_depth)

                for result in self._find(pattern, current=subdir, system=system,
                                         nodes=nodes, systems=systems,
                                         curr_depth=sub_depth, extra=extra,
                                         exclude=exclude,
                                         depth=depth, full_match=full_match):
                    yield result
