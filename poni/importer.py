"""
debian .deb package importer

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

import logging
import os
from . import errors

try:
    import apt_inst
except ImportError:
    apt_inst = None


class Importer(object):
    def __init__(self, source, verbose=False):
        self.log = logging.getLogger("importer")
        self.source = source
        self.verbose = verbose

    def import_to(self, confman):
        assert 0, "override in sub-class"


class DebImporter(Importer):
    def __init__(self, source, verbose=False):
        Importer.__init__(self, source, verbose=verbose)
        if not apt_inst:
            raise errors.MissingLibraryError(
                "this feature requires the 'python-apt' library")

    def import_to(self, confman):
        try:
            return self.__import_to(confman)
        except (OSError, IOError) as error:
            raise errors.ImporterError("importing from '%s' failed: %s: %s" % (
                self.source, error.__class__.__name__, error))

    def __import_to(self, confman):
        prefix = "usr/lib/poni-config/"

        def callback(member, contents):
            if member.name.endswith("/") or not member.name.startswith(prefix):
                # not a poni-config file, skip
                return

            dest_sub = member.name[len(prefix):]
            dest_path = os.path.join(confman.system_root, dest_sub)
            dest_dir = os.path.dirname(dest_path)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)

            write = not os.path.exists(dest_path)
            if (not write) and os.path.exists(dest_path):
                old = open(dest_path).read()
                write = (old != contents)

            logger = self.log.info if self.verbose else self.log.debug
            pretty_path = os.path.relpath(dest_path, start=confman.root_dir)
            if write:
                open(dest_path, "wb").write(contents)
                logger("imported: %s", pretty_path)
            else:
                logger("unchanged: %s", pretty_path)

        data_tar = apt_inst.DebFile(open(self.source)).data
        # reads each file into memory and calls the callback, but there's no file-object based option...
        data_tar.go(callback)  # pylint: disable=E1101


def get_importer(source_path, **kwargs):
    if os.path.isdir(source_path):
        assert 0, "unimplemented"
    elif os.path.isfile(source_path) and source_path.endswith(".deb"):
        return DebImporter(source_path, **kwargs)
    else:
        raise errors.ImporterError(
            "don't know how to import '%s'" % source_path)
