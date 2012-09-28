"""
debian .deb package importer

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

import logging
from path import path
from . import errors

try:
    import apt_inst
except ImportError:
    apt_inst = None

class Importer:
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
        except (OSError, IOError), error:
            raise errors.ImporterError("importing from '%s' failed: %s: %s" % (
                self.source, error.__class__.__name__, error))

    def __import_to(self, confman):
        prefix = "usr/lib/poni-config/"
        def callback(member, contents):
            if member.name.endswith("/") or not member.name.startswith(prefix):
                # not a poni-config file, skip
                return

            dest_sub = member.name[len(prefix):]
            dest_path = confman.system_root / dest_sub
            dest_dir = dest_path.dirname()
            if not dest_dir.exists():
                dest_dir.makedirs()

            write = not dest_path.exists()
            if (not write) and dest_path.exists():
                old = dest_path.bytes()
                write = (old != contents)

            logger = self.log.info if self.verbose else self.log.debug
            pretty_path = confman.root_dir.relpathto(dest_path)
            if write:
                file(dest_path, "wb").write(contents)
                logger("imported: %s", pretty_path)
            else:
                logger("unchanged: %s", pretty_path)

        data_tar = apt_inst.DebFile(file(self.source)).data
        # reads each file into memory and calls the callback, but there's no file-object based option...
        data_tar.go(callback)

def get_importer(source_path, **kwargs):
    source_path = path(source_path)
    if source_path.isdir():
        assert 0, "unimplemented"
    elif source_path.isfile() and source_path.endswith(".deb"):
        return DebImporter(source_path, **kwargs)
    else:
        raise errors.ImporterError(
            "don't know how to import '%s'" % source_path)
