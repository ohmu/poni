"""
Multi-layer settings management

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

TODO: this simple draft is VERY likely to change a lot

"""

import glob
import os
import logging
from . import errors
from .util import json


class Config(dict):
    def __init__(self, config_dir):
        dict.__init__(self)
        self.log = logging.getLogger("config")
        self.config_dir = config_dir
        self.config = None
        self.reload()

    def reload(self):
        if not self.config_dir.exists():
            return

        files = sorted(glob.glob(os.path.join(self.config_dir, "*.json")))
        self.log.debug("settings files: %r", files)
        for file_path in files:
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
