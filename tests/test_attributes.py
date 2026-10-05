"""
测试六维属性值对象。

不需要游戏数据库。

运行: python -m pytest tests/test_attributes.py -v
  或: python tests/test_attributes.py
"""

import os
import sqlite3
import sys
import tempfile

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.attributes import FIELDS, LABELS, TOTAL_SQL, SixAttributes


def test_from_list_order():
    """from_list 按 FIELDS 的顺序（体力在前）"""
    attrs = SixAttributes.from_list([71, 108, 70, 101, 77, 105])
    assert attrs.hp == 71
    assert attrs.atk == 108
    assert attrs.def_ == 70
    assert attrs.sp_atk == 101
    assert attrs.sp_def == 77
    assert attrs.spd == 105


def test_fields_order_is_the_invariant():
    """as_dict 的键顺序必须和 FIELDS 一致 —— 这是整个模块的隐含契约。

    FIELDS 同时被 top_n 拿来拼 SQL 表达式，一旦 dataclass 的字段顺序
    和 FIELDS 对不上，所有数值都会串位。
    """
    attrs = SixAttributes.from_list([1, 2, 3, 4, 5, 6])
    assert attrs.as_dict() == dict(zip(FIELDS, [1, 2, 3, 4, 5, 6]))


def test_total():
    """种族值总和"""
    assert SixAttributes.from_list([71, 108, 70, 101, 77, 105]).total == 532
    # 真实数据里的一个极端值: 六项全是 180
    assert SixAttributes.from_list([180] * 6).total == 1080
    assert SixAttributes().total == 0


def test_total_sql_matches_fields():
    """TOTAL_SQL 必须真的是 FIELDS 的求和，不能手写漏项"""
    assert TOTAL_SQL == ' + '.join(FIELDS)
    assert len(FIELDS) == 6


def test_labels_cover_all_fields():
    """每个列名都要有中文标签，否则展示时会 KeyError"""
    assert set(LABELS) == set(FIELDS)


def test_from_row_dict():
    attrs = SixAttributes.from_row(
        {'HP': 55, 'Atk': 69, 'Def': 65, 'SpAtk': 45, 'SpDef': 55, 'Spd': 31}
    )
    assert attrs.hp == 55
    assert attrs.spd == 31
    assert attrs.total == 320


def test_from_row_sqlite_row():
    """sqlite3.Row 也要能直接喂进来"""
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(os.path.join(tmp, 'x.db'))
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE m (HP INT, Atk INT, Def INT, SpAtk INT, SpDef INT, Spd INT)')
        conn.execute('INSERT INTO m VALUES (71, 108, 70, 101, 77, 105)')
        row = conn.execute('SELECT * FROM m').fetchone()
        attrs = SixAttributes.from_row(row)
        conn.close()
    assert attrs.total == 532


def test_from_row_missing_columns_are_zero():
    """只 SELECT 了一部分列时，缺的按 0 处理，不能抛异常"""
    attrs = SixAttributes.from_row({'HP': 100, 'Atk': 50})
    assert attrs.hp == 100
    assert attrs.atk == 50
    assert attrs.def_ == 0
    assert attrs.total == 150


def test_from_row_handles_none():
    attrs = SixAttributes.from_row({'HP': None, 'Atk': 50})
    assert attrs.hp == 0
    assert attrs.total == 50


def test_from_list_too_short():
    try:
        SixAttributes.from_list([1, 2, 3])
        assert False, "少于 6 个应该报错"
    except ValueError as e:
        assert '6' in str(e)


def test_is_frozen():
    """值对象不可变 —— 拿到手就不会被别处改掉"""
    attrs = SixAttributes.from_list([1, 2, 3, 4, 5, 6])
    try:
        attrs.hp = 999
        assert False, "应该抛 FrozenInstanceError"
    except Exception as e:
        assert 'frozen' in type(e).__name__.lower() or 'cannot assign' in str(e).lower()


def test_str():
    text = str(SixAttributes.from_list([71, 108, 70, 101, 77, 105]))
    assert '体力:71' in text
    assert '速度:105' in text


# ──────────────────────────────────────────
#  独立运行
# ──────────────────────────────────────────

_TESTS = [
    test_from_list_order,
    test_fields_order_is_the_invariant,
    test_total,
    test_total_sql_matches_fields,
    test_labels_cover_all_fields,
    test_from_row_dict,
    test_from_row_sqlite_row,
    test_from_row_missing_columns_are_zero,
    test_from_row_handles_none,
    test_from_list_too_short,
    test_is_frozen,
    test_str,
]


if __name__ == '__main__':
    passed = 0
    for test in _TESTS:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
        except Exception as e:
            print(f"  💥 {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(_TESTS)} 通过")
    sys.exit(0 if passed == len(_TESTS) else 1)
