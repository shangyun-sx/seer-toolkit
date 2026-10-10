"""
测试 sqlite 连接管理（database/connections.py）。

这个模块此前只有间接覆盖（test_pokedex 里那些并发用例）。这里直接测它自己
的两件事：连接上的 PRAGMA 调优有没有生效，以及「每线程一条」的语义。

运行: python -m pytest tests/test_connections.py -v
  或: python tests/test_connections.py
"""

import os
import sqlite3
import sys
import tempfile
import threading

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.connections import ThreadLocalConnections


def _make_db(data_dir, name='Monster.db'):
    """造一个最小的库 —— 只要够开连接就行"""
    conn = sqlite3.connect(os.path.join(data_dir, name))
    conn.execute("CREATE TABLE t (ID INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t VALUES (?,?)", ((i, f'x{i}') for i in range(50)))
    conn.commit()
    conn.close()


class _dir:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        _make_db(self._tmp.name)
        return self._tmp.name

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False


# ──────────────────────────────────────────
#  PRAGMA 调优
# ──────────────────────────────────────────

def test_connections_are_tuned():
    """新连接必须带上调优后的 PRAGMA。

    这两项不是可有可无的：SQLite 默认页缓存 2MB，比这里任何一个库都小，
    回退到默认值时查询会慢一个数量级（主键查一行 25ms vs 0.7ms）。
    所以这条测试盯的是「别被人顺手删掉」。
    """
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        try:
            conn = conns.get('Monster.db')

            cache_size = conn.execute('PRAGMA cache_size').fetchone()[0]
            mmap_size = conn.execute('PRAGMA mmap_size').fetchone()[0]

            assert cache_size < 0, f'cache_size 应当是负数(KB 单位)，实际 {cache_size}'
            assert abs(cache_size) >= 8000, f'页缓存至少要 8MB，实际 {-cache_size/1000:.1f}MB'
            assert mmap_size > 0, f'mmap_size 应当打开，实际 {mmap_size}'
        finally:
            conns.close()


def test_tuning_survives_reopen():
    """close() 之后再取连接，仍然是调优过的"""
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        try:
            conns.get('Monster.db')
            conns.close()
            conn = conns.get('Monster.db')
            assert conn.execute('PRAGMA cache_size').fetchone()[0] < 0
            assert conn.execute('PRAGMA mmap_size').fetchone()[0] > 0
        finally:
            conns.close()


# ──────────────────────────────────────────
#  每线程一条
# ──────────────────────────────────────────

def test_same_thread_reuses_the_connection():
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        try:
            assert conns.get('Monster.db') is conns.get('Monster.db')
            assert conns.open_count() == 1
        finally:
            conns.close()


def test_each_thread_gets_its_own_connection():
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        seen = []

        def worker():
            seen.append(conns.get('Monster.db'))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        try:
            assert len({id(c) for c in seen}) == 4, '四个线程应当拿到四条不同的连接'
            assert conns.open_count() == 4
        finally:
            conns.close()


def test_close_releases_everything():
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        t = threading.Thread(target=lambda: conns.get('Monster.db'))
        t.start()
        t.join()
        conns.get('Monster.db')          # 主线程也开一条

        assert conns.open_count() == 2
        conns.close()
        assert conns.open_count() == 0


def test_close_is_idempotent():
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        conns.get('Monster.db')
        conns.close()
        conns.close()                    # 再来一次不该炸
        assert conns.open_count() == 0


# ──────────────────────────────────────────
#  缺文件
# ──────────────────────────────────────────

def test_missing_file_raises_with_the_path():
    with _dir() as data_dir:
        conns = ThreadLocalConnections(data_dir)
        try:
            try:
                conns.get('Nope.db')
                assert False, '应当抛 FileNotFoundError'
            except FileNotFoundError as e:
                assert 'Nope.db' in str(e), f'报错里应当带上路径: {e}'
        finally:
            conns.close()


if __name__ == '__main__':
    tests = [
        test_connections_are_tuned,
        test_tuning_survives_reopen,
        test_same_thread_reuses_the_connection,
        test_each_thread_gets_its_own_connection,
        test_close_releases_everything,
        test_close_is_idempotent,
        test_missing_file_raises_with_the_path,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  OK   {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {test.__name__}: {e}")
        except Exception as e:
            print(f"  💥   {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
