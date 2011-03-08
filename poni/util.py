"""
Generic utility functions and classes

Copyright (c) 2010-2011 Mika Eloranta
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


DEF_VALUE = object() # used as default value where None cannot be used


# TODO: refactor and write tests for get_dict_prop/set_dict_prop
def get_dict_prop(item, address, verify=False):
    error = False
    for part in address[:-1]:
        if not isinstance(item, dict):
            error = True
            break

        old = item.get(part, DEF_VALUE)
        if old is DEF_VALUE:
            if verify:
                error = True
                break

            item = item.setdefault(part, {})
        else:
            item = old

    if error or (not isinstance(item, dict)):
        raise errors.InvalidProperty(
            "%r does not exist" % (".".join(address)))

    old = item.get(address[-1], DEF_VALUE)

    return item, old


def set_dict_prop(item, address, value, verify=False, schema=None):
    item, old = get_dict_prop(item, address, verify=verify)
    if verify and (old is DEF_VALUE) and (schema is not None):
        schema_item, old = get_dict_prop(schema, address, verify=verify)
        return set_dict_prop(item, address, value, verify=False)

    if verify:
        if old is DEF_VALUE:
            raise errors.InvalidProperty(
                "%r does not exist" % (".".join(address)))
        elif type(value) != type(old):
            raise errors.InvalidProperty("%r type is %r, got %r: %r" % (
                    ".".join(address), type(old).__name__,
                    type(value).__name__, value))
    else:
        if old is DEF_VALUE:
            old = None

        item[address[-1]] = value

    return old


def json_dump(data, file_path):
    """safe json dump to file, writes to temp file first"""
    temp_path = "%s.json_dump.tmp" % file_path
    with file(temp_path, "wb") as out:
        json.dump(data, out, indent=4, sort_keys=True)

    os.rename(temp_path, file_path)


def parse_prop(prop_str, converters=None):
    """
    parse and return (keyname, value) from input 'prop_str'

    'prop_str' may contain converters, for example:

      'foo=hello' => ('foo', 'hello')
      'bar:int=123' => ('bar', 123)
    """
    val_parts = prop_str.split("=", 1)
    if len(val_parts) == 1:
        # no value specified
        name = prop_str
        value = None
    else:
        name, value = val_parts

    parts = name.split(":", 1)
    try:
        if len(parts) > 1:
            name, enc_str = parts
            codec = recode.Codec(enc_str, default=recode.ENCODE,
                                 converters=converters)
        else:
            codec = recode.Codec("-ascii")

        out = name, codec.process(value)
    except (ValueError, recode.Error), error:
        raise errors.InvalidProperty("%s: %s" % (error.__class__.__name__,
                                                 error))

    return out


def parse_count(count_str):
    """parse and return integers (start, end) from input 'N' or 'N..M'"""
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
    """return a statistics dict about a directory and its contents"""
    out = {"path": dir_path, "file_count": 0, "total_bytes": 0}
    for file_path in path(dir_path).walkfiles():
        out["file_count"] += 1
        out["total_bytes"] += file_path.stat().st_size

    return out


def path_iter_dict(dict_obj, prefix=[]):
    """
    yield (path, value) for each item in a dict possibly containing other dicts

    'path' is in format 'key1.key2.valuename'
    """
    for key, value in sorted(dict_obj.iteritems()):
        location = prefix + [key]
        if isinstance(value, dict):
            for item in path_iter_dict(value, prefix=location):
                yield item
        else:
            yield ".".join(location), value
