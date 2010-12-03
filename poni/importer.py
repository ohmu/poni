import logging
import shutil
from path import path
from . import errors

try:
    from debian import debfile
except ImportError:
    debfile = None

class Importer:
    def __init__(self, source):
        self.log = logging.getLogger("importer")
        self.source = source

    def import_to(self, confman):
        assert 0, "override in sub-class"


class DebImporter(Importer):
    def __init__(self, source):
        Importer.__init__(self, source)
        if not debfile:
            raise errors.MissingLibraryError(
                "this feature requires the 'python-debian' library")

    def import_to(self, confman, verbose=False):
        data = debfile.DebFile(self.source).data.tgz()

        prefix = "./usr/lib/poni-config/"
        for item in data.getnames():
            if (item.endswith("/") or (not item.startswith(prefix))
                or (not data.getmember(item).isfile())):
                continue

            dest_sub = item[len(prefix):]
            dest_path = confman.system_root / dest_sub
            dest_dir = dest_path.dirname()
            if not dest_dir.exists():
                dest_dir.makedirs()

            contents = data.extractfile(item).read()
            write = not dest_path.exists()
            if (not write) and dest_path.exists():
                old = dest_path.bytes()
                write = (old != contents)

            if write:
                file(dest_path, "wb").write(contents)
            elif verbose:
                self.log.info("unchanged: %s", dest_path)


def get_importer(source_path):
    source_path = path(source_path)
    if source_path.isdir():
        assert 0, "unimplemented"
    elif source_path.isfile() and source_path.endswith(".deb"):
        return DebImporter(source_path)
    else:
        raise errors.ImporterError(
            "don't know how to import '%s'" % source_path)
