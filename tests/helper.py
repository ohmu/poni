import itertools
import shutil
import os
import tempfile
from path import path


class Helper:
    def __init__(self):
        self.temp_files = []

    def temp_file(self, prefix="test_poni"):
        f = tempfile.mktemp(prefix=prefix)
        self.temp_files.append(f)
        return path(f)

    def setup(self):
        pass

    def teardown(self):
        for temp_file in self.temp_files:
            if os.path.isfile(temp_file):
                os.unlink(temp_file)
            elif os.path.isdir(temp_file):
                shutil.rmtree(temp_file)


def combos(seq):
    seq = list(seq)
    for length in range(0, len(seq) + 1):
        for combo in itertools.combinations(seq, length):
            yield combo


