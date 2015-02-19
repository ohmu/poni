from poni import util
import os


def test_dir_stats():
    poni_src_dir = os.path.dirname(os.path.dirname(__file__))
    stats = util.dir_stats(poni_src_dir)
    assert stats['file_count'] > 30
    assert stats['total_bytes'] > 100000
    assert stats['path'] == poni_src_dir
