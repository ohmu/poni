"""
Multi-layer settings management

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

TODO: this simple draft is VERY likely to change a lot

"""

import logging
from path import path
from . import errors
from .util import json


class Config(dict):
    def __init__(self, config_dirs):
        dict.__init__(self)
        self.log = logging.getLogger("config")
        self.config_dirs = list(config_dirs)
        self.layers = []
        self.reload()

    def reload(self):
        self.clear()
        self.layers = []
        # when combinining settings from multiple files, they are primarily
        # sorted by the filename prefix (first two letters) and secondarily
        # by the inheritance order (parent before child)
        for i, (layer_name, config_dir) in enumerate(self.config_dirs):
            config_dir = path(config_dir)
            if config_dir.exists():
                for file_path in config_dir.glob("*.json"):
                    self.layers.append(((file_path.basename()[:2], i),
                                        layer_name, file_path))

        self.layers.sort()

        self.log.debug("settings files: %r", self.layers)
        for sort_key, layer_name, file_path in self.layers:
            try:
                config_dict = json.load(file(file_path, "rb"))
            except ValueError, error:
                raise errors.SettingsError("%s: %s: %s" % (
                        file_path, error.__class__.__name__, error))

            self.log.debug("loaded %r: %r", file_path, config_dict)
            if not self:
                # base config (defaults)
                self.update(config_dict)
            else:
                self.apply_update(config_dict, self, file_path)

    def apply_update(self, update, target, file_path):
        self.log.debug("apply update: %r -> %r", update, target)
        if not isinstance(update, dict):
            raise errors.SettingsError("%s: expected dict, got %s (%r)" % (
                    file_path, type(update), update))

        for key, value in update.iteritems():
            first = key[:1]
            if key[:1] in ["!", "+", "-"]:
                try:
                    target_value = target[key[1:]]
                except KeyError:
                    raise errors.SettingsError(
                        "%s: cannot override missing setting %r" % (
                            file_path, key))

                if first == "!":
                    target[key[1:]] = value
                elif first == "+":
                    target_value.extend(value)
                else: # "-"
                    for remove_key in value:
                        if remove_key in target_value:
                            target_value.remove(remove_key)
            else:
                if key not in target:
                    raise errors.SettingsError(
                        "%s: unknown setting %r (not in default settings)" % (
                            file_path, key))

                self.apply_update(target[key], value, file_path)


class Proxy:
    def __init__(self, target):
        self.target = target

    def __getattr__(self, item):
        target = self.target
        for part in item.split("."):
            target = target[part]

        return target
