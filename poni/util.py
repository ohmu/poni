"""
Generic utility functions and classes

Copyright (c) 2010 Mika Eloranta
See LICENSE for details.

"""

import os
from path import path
from . import errors
from . import recode
import socket

try:
    import json
except ImportError:
    import simplejson as json


def set_dict_prop(item, address, value, verify=False):
    def_value = object()
    for part in address[:-1]:
        old = item.get(part, def_value)
        if old is def_value:
            if verify:
                raise errors.InvalidProperty(
                    "%r does not exist" % (".".join(address)))

            item = item.setdefault(part, {})
        else:
            item = old

    old = item.get(address[-1], def_value)
    if verify:
        if old is def_value:
            raise errors.InvalidProperty(
                "%r does not exist" % (".".join(address)))
        elif type(value) != type(old):
            raise errors.InvalidProperty("%r type is %r, got %r: %r" % (
                    ".".join(address), type(old).__name__,
                    type(value).__name__, value))
    else:
        if old is def_value:
            old = None

        item[address[-1]] = value

    return old


def json_dump(data, output):
    json.dump(data, output, indent=4, sort_keys=True)

def parse_prop(prop_str):
    try:
        name, value = prop_str.split("=", 1)
    except ValueError:
        raise errors.InvalidProperty(
            "invalid property: %r, expected format: name=[type:]value" %
            prop_str)

    parts = name.split(":", 1)
    try:
        if len(parts) > 1:
            name, enc_str = parts
            codec = recode.Codec(enc_str, default=recode.ENCODE)
        else:
            codec = recode.Codec("-ascii")

        out = name, codec.process(value)
    except (ValueError, recode.Error), error:
        raise errors.InvalidProperty("%s: %s" % (error.__class__.__name__,
                                                 error))
    
    return out
    
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

def path_iter_dict(dict_obj, prefix=[]):
    for key, value in sorted(dict_obj.iteritems()):
        location = prefix + [key]
        if isinstance(value, dict):
            for item in path_iter_dict(value, prefix=location):
                yield item
        else:
            yield ".".join(location), value
