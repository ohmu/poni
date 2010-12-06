"""
Generic utility functions and classes

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

import os
from path import path
from . import errors

try:
    import json
except ImportError:
    import simplejson as json


def set_dict_prop(item, address, value):
    for part in address[:-1]:
        old = item.get(part)
        if old is None:
            item = item.setdefault(part, {})
        else:
            item = old

    old = item.get(address[-1])
    item[address[-1]] = value
    return old


def json_dump(data, output):
    json.dump(data, output, indent=4, sort_keys=True)


BOOL_MAP = {"true":True, "1":True, "on":True,
            "false":False, "0":False, "off":False}

def to_bool(value):
    try:
        return BOOL_MAP[value.lower()]
    except KeyError:
        raise errors.InvalidProperty("invalid boolean value: %r" % (value,))

def from_env(value):
    try:
        return os.environ[value]
    except KeyError:
        raise errors.InvalidProperty("environment variable %r not set" % value)

PROP_PREFIX = {
    "int:": int,
    "float:": float,
    "bool:": to_bool,
    "env:": from_env,
    }

def parse_prop(prop_str):
    try:
        name, value = prop_str.split("=", 1)
    except ValueError:
        raise errors.InvalidProperty("invalid property: %r" % prop_str)

    for prefix, convert in PROP_PREFIX.iteritems():
        if value.startswith(prefix):
            try:
                value = convert(value[len(prefix):])
            except ValueError, error:
                raise errors.InvalidProperty(
                    "invalid property value %r: %s: %s" % (
                        value, error.__class__.__name__, error))
            break

    return name, value


def parse_count(count_str):
    ranges = count_str.split("..")
    try:
        if len(ranges) == 1:
            return 1, (int(count_str) + 1)
        elif len(ranges) == 2:
            return int(ranges[0]), (int(ranges[1]) + 1)
    except ValueError:
        pass

    raise errors.InvalidRange("invalid range: %r" % (count_str,))


def format_error(error):
    return "ERROR: %s: %s" % (error.__class__.__name__, error)

def dir_stats(dir_path):
    out = {"path": dir_path, "file_count": 0, "total_bytes": 0}
    for file_path in path(dir_path).walkfiles():
        out["file_count"] += 1
        out["total_bytes"] += file_path.stat().st_size

    return out
