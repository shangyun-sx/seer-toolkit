"""
测试数据库完整性校验（database/integrity.py）。

这个模块此前一项测试都没有 —— 它干的事是「拿 Data.ini 里记的 MD5 核对磁盘
上的文件」，出错的表现是「明明没坏却报不匹配」，或者更糟：核对错了文件还以为
通过了。

运行: python -m pytest tests/test_integrity.py -v
  或: python tests/test_integrity.py
"""

import hashlib
import os
import sys
import tempfile

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.integrity import IntegrityChecker


def _write(path: str, data: bytes) -> str:
    """写文件并返回它的 md5"""
    with open(path, 'wb') as f:
        f.write(data)
    return hashlib.md5(data).hexdigest()


def _make_fake_data_dir(tmp: str) -> None:
    """造一个最小的 data 目录。

    key 刻意取得和文件名对不上，复现雷小伊的真实情况：
        Data.ini 写 Monsters -> 磁盘上是 Monster.db（单复数）
        Data.ini 写 mintmark -> 磁盘上是 MintMarks.db（大小写 + 单复数）
    这两个 key 走不了精确匹配，只能靠部分匹配那一步。
    """
    hashes = {
        'Monsters': _write(os.path.join(tmp, 'Monster.db'), b'monster-data'),
        'mintmark': _write(os.path.join(tmp, 'MintMarks.db'), b'mintmark-data'),
        'Moves': _write(os.path.join(tmp, 'Moves.db'), b'moves-data'),
        'version': _write(os.path.join(tmp, 'version'), b'1.2.3'),
    }
    with open(os.path.join(tmp, 'Data.ini'), 'w', encoding='gbk') as f:
        f.write('[Config]\n')
        for key, digest in hashes.items():
            f.write(f'{key}={digest}\n')


# ──────────────────────────────────────────
#  文件名匹配
# ──────────────────────────────────────────

def test_find_file_handles_plural_and_case():
    """部分匹配必须工作 —— 它就是为 Monsters / mintmark 存在的，别删"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_data_dir(tmp)
        checker = IntegrityChecker(tmp)

        assert checker._find_file('Monsters') == 'Monster.db'
        assert checker._find_file('mintmark') == 'MintMarks.db'
        assert checker._find_file('Moves') == 'Moves.db'
        assert checker._find_file('version') == 'version'      # 无后缀文件
        assert checker._find_file('没有这个key') is None


def test_fuzzy_match_is_deterministic():
    """候选多于一个时，结果不能取决于 os.listdir 的返回顺序。

    旧实现是在循环里「撞到第一个就返回」，而 file_map 的顺序来自
    os.listdir —— 同一份数据在不同机器上可能给出不同答案，甚至核对到
    另一个文件却以为通过了。这里让两个候选同时出现，验证选的是名字最
    接近的那个。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, 'Monster.db'), b'a')
        _write(os.path.join(tmp, 'MonsterSkill.db'), b'b')
        with open(os.path.join(tmp, 'Data.ini'), 'w', encoding='gbk') as f:
            f.write('[Config]\nmonsters=deadbeef\n')

        # 'monsters' 与 'monster' 长度差 1，与 'monsterskill' 差 5 -> 选前者
        assert IntegrityChecker(tmp)._find_file('monsters') == 'Monster.db'


# ──────────────────────────────────────────
#  verify()
# ──────────────────────────────────────────

def test_verify_all_matching():
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_data_dir(tmp)
        ok, matched, mismatched = IntegrityChecker(tmp).verify()

        assert ok is True, f'应当全通过，异常项: {mismatched}'
        assert len(matched) == 4
        assert not mismatched


def test_verify_detects_tampering():
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_data_dir(tmp)
        with open(os.path.join(tmp, 'Monster.db'), 'wb') as f:
            f.write(b'TAMPERED')

        ok, matched, mismatched = IntegrityChecker(tmp).verify()

        assert ok is False
        statuses = {m['filename']: m['status'] for m in mismatched}
        assert statuses.get('Monster.db') == '哈希不匹配'
        assert len(matched) == 3


def test_verify_reports_unregistered_files():
    """磁盘上有、Data.ini 里没登记的，要单独报出来"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_data_dir(tmp)
        _write(os.path.join(tmp, 'Extra.db'), b'extra')

        ok, matched, mismatched = IntegrityChecker(tmp).verify()

        assert ok is False
        extra = [m for m in mismatched if m['filename'] == 'Extra.db']
        assert len(extra) == 1, f'Extra.db 没被报出来: {mismatched}'
        assert extra[0]['status'] == '未在 Data.ini 中登记'


def test_verify_reports_missing_files():
    """Data.ini 登记了、但磁盘上没有的"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_data_dir(tmp)
        os.remove(os.path.join(tmp, 'Moves.db'))

        ok, matched, mismatched = IntegrityChecker(tmp).verify()

        missing = [m for m in mismatched if m['status'] == '文件不存在']
        assert len(missing) == 1, f'应当报 Moves 缺失: {mismatched}'
        assert missing[0]['key'] == 'Moves'


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_find_file_handles_plural_and_case,
        test_fuzzy_match_is_deterministic,
        test_verify_all_matching,
        test_verify_detects_tampering,
        test_verify_reports_unregistered_files,
        test_verify_reports_missing_files,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
        except Exception as e:
            print(f"  💥 {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
