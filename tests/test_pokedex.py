"""
测试精灵图鉴查询器。

分两部分:
  * 离线测试 —— 用内存里临时造的 Monster.db，不需要游戏数据库
  * 在线测试 —— 需要雷小伊的 data/*.db，传入目录才会跑

运行: python -m pytest tests/test_pokedex.py -v
  或: python tests/test_pokedex.py                       # 只跑离线测试
  或: python tests/test_pokedex.py <雷小伊目录>            # 离线 + 在线
"""

import os
import sqlite3
import sys
import tempfile

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.pokedex import Pokedex


# ──────────────────────────────────────────
#  离线测试: 临时造一个 Monster.db
# ──────────────────────────────────────────

# 造几条覆盖单属性 / 双属性 / 皮肤的数据
#   Type 存的是「属性组合 ID」: 3=火, 5=电, 33=电·火, 21=草·超能
_FAKE_MONSTERS = [
    # ID,  名称,      Type, HP, Atk, Def, SpAtk, SpDef, Spd
    (1, '雷伊', 5, 70, 120, 80, 110, 80, 130),
    (2, '火猴', 3, 60, 100, 70, 100, 70, 90),
    (3, '电火兽', 33, 90, 110, 85, 105, 85, 100),   # 双属性 电·火
    (4, '草超能怪', 21, 80, 95, 90, 115, 95, 105),  # 双属性 草·超能
    (15001, '雷伊皮肤', 5, 70, 120, 80, 110, 80, 130),  # 皮肤，应被排除
]

_FAKE_MOVES = [
    (1, '电光一闪', 5, '物理', 40, 30, 100),
    (2, '火焰冲击', 3, '特殊', 90, 15, 100),
]

# 真实数据里 Moves 是带学习等级的 JSON 数组（对应 SeerAPI 的 SkillInPet）
_MOVES_JSON = ('[{"ID":2,"LearningLv":5,"Rec":0,"Tag":0},'
               ' {"ID":1,"LearningLv":1,"Rec":0,"Tag":0}]')


def _make_fake_db(data_dir: str) -> None:
    """在 data_dir 下造一套最小的 Monster.db / Moves.db"""
    conn = sqlite3.connect(os.path.join(data_dir, 'Monster.db'))
    conn.execute(
        "CREATE TABLE monsters (ID INTEGER PRIMARY KEY, DefName TEXT, Type INTEGER, "
        "HP INTEGER, Atk INTEGER, Def INTEGER, SpAtk INTEGER, SpDef INTEGER, "
        "Spd INTEGER, Moves TEXT, Gender INTEGER, IsDark INTEGER)"
    )
    conn.executemany(
        "INSERT INTO monsters VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [row + (_MOVES_JSON, 0, 0) for row in _FAKE_MONSTERS],
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(os.path.join(data_dir, 'Moves.db'))
    conn.execute(
        "CREATE TABLE moves (ID INTEGER PRIMARY KEY, Name TEXT, Type INTEGER, "
        "Category TEXT, Power INTEGER, MaxPP INTEGER, Accuracy INTEGER)"
    )
    conn.executemany("INSERT INTO moves VALUES (?,?,?,?,?,?,?)", _FAKE_MOVES)
    conn.commit()
    conn.close()


def _with_fake_db(fn):
    """把临时数据库目录传给测试函数，结束后清理"""
    def wrapper():
        with tempfile.TemporaryDirectory() as tmp:
            _make_fake_db(tmp)
            dex = Pokedex(tmp)
            try:
                fn(dex)
            finally:
                dex.close()
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@_with_fake_db
def test_count_excludes_skins(dex):
    """皮肤 (ID >= 15000) 不计入总数"""
    assert dex.count() == 4, f"应该只有 4 只非皮肤精灵，实际 {dex.count()}"


@_with_fake_db
def test_search(dex):
    """按名字模糊搜索"""
    results = dex.search('雷')
    names = [r['DefName'] for r in results]
    assert names == ['雷伊'], f"皮肤不该被搜出来: {names}"


@_with_fake_db
def test_type_name_is_filled_in(dex):
    """查询结果里要带可读的属性名"""
    monkey = dex.search('火猴')[0]
    assert monkey['TypeName'] == '火', monkey
    assert dex.search('雷伊')[0]['TypeName'] == '电'


@_with_fake_db
def test_filter_single_type(dex):
    """按单属性筛选"""
    fire = dex.filter_by_type('火')
    names = {r['DefName'] for r in fire}
    assert names == {'火猴', '电火兽'}, f"火系应该包含双属性的电火兽: {names}"


@_with_fake_db
def test_filter_type_includes_dual(dex):
    """双属性精灵能被自己的任一属性筛到"""
    electric = {r['DefName'] for r in dex.filter_by_type('电')}
    assert '雷伊' in electric and '电火兽' in electric

    grass = {r['DefName'] for r in dex.filter_by_type('草')}
    assert grass == {'草超能怪'}, f"草系应该只有草超能怪: {grass}"


@_with_fake_db
def test_filter_dual_type_exact(dex):
    """按双属性筛选是精确匹配"""
    combo = {r['DefName'] for r in dex.filter_by_type('电·火')}
    assert combo == {'电火兽'}, f"电·火 应该只有电火兽: {combo}"

    # 认不出来的属性要明确报错，而不是静默返回空 —— 否则「火系」这种
    # 笔误会被当成「没有精灵」，把问题藏起来
    try:
        dex.filter_by_type('火系')
        assert False, "无法识别的属性应该抛 ValueError"
    except ValueError as e:
        assert '火系' in str(e)


@_with_fake_db
def test_types_of(dex):
    """从数据库行里解析属性"""
    assert Pokedex.types_of(dex.get_by_id(2)) == (3,), "火猴是单属性火"
    assert Pokedex.types_of(dex.get_by_id(3)) == (5, 3), "电火兽是 电·火"
    assert Pokedex.types_of(dex.get_by_id(4)) == (1, 10), "草超能怪是 草·超能"
    assert Pokedex.types_of(None) == ()


@_with_fake_db
def test_get_monster_types(dex):
    assert dex.get_monster_types(3) == (5, 3)
    assert dex.get_monster_types(99999) == (), "不存在的精灵返回空"


@_with_fake_db
def test_type_effectiveness(dex):
    """属性克制资料"""
    data = dex.get_type_effectiveness(3)   # 电·火
    assert data['label'] == '电·火'
    assert data['types'] == [5, 3]

    weak = dict(data['weaknesses'])
    assert weak.get('圣灵') == 4.0, f"电·火 应该 4 倍弱圣灵: {weak}"
    assert weak.get('地面') == 4.0

    # 单属性精灵
    fire = dex.get_type_effectiveness(2)
    assert fire['label'] == '火'
    assert dict(fire['weaknesses']).get('水') == 2.0

    # 不存在的精灵
    assert dex.get_type_effectiveness(99999) is None


@_with_fake_db
def test_get_moves(dex):
    """跨库查询技能，并带回学习等级"""
    moves = dex.get_moves(1)
    names = {m['Name'] for m in moves}
    assert names == {'电光一闪', '火焰冲击'}, names

    # 按学习等级排序: 火焰冲击(5级) 在 电光一闪(1级) 后面
    assert [m['Name'] for m in moves] == ['电光一闪', '火焰冲击'], moves
    assert moves[0]['LearningLv'] == 1
    assert moves[1]['LearningLv'] == 5
    # 技能属性 / 类别也要有可读名
    assert moves[0]['TypeName'] == '电'
    assert moves[1]['TypeName'] == '火'
    assert moves[1]['CategoryName'] == '特殊'   # Category=2


def test_parse_move_entries():
    """Moves 列的两种格式都要能解析"""
    # 真实的 JSON 数组格式
    entries = Pokedex.parse_move_entries(
        '[{"ID":10006,"LearningLv":1,"Rec":0,"Tag":0},'
        ' {"ID":20006,"LearningLv":4,"Rec":0,"Tag":0}]'
    )
    assert [e['ID'] for e in entries] == [10006, 20006]
    assert entries[1]['LearningLv'] == 4

    # 逗号分隔的老格式
    assert [e['ID'] for e in Pokedex.parse_move_entries('1,2,3')] == [1, 2, 3]
    # 纯 ID 的 JSON 数组
    assert [e['ID'] for e in Pokedex.parse_move_entries('[1, 2]')] == [1, 2]

    # 空值 / 坏数据都不能炸
    for bad in (None, '', '   ', '[]', 'not json', '[{"no_id":1}]'):
        assert Pokedex.parse_move_entries(bad) == [], bad


@_with_fake_db
def test_top_n(dex):
    top = dex.top_n('Spd', 2)
    assert top[0]['DefName'] == '雷伊', top
    assert top[0]['TypeName'] == '电'


@_with_fake_db
def test_sql_injection_blocked(dex):
    """SQL 注入防护"""
    for bad in ('HP; DROP TABLE monsters;--', '1; DROP TABLE monsters;--'):
        try:
            dex.top_n(bad)
            assert False, f"{bad!r} 应该被拦截"
        except ValueError as e:
            assert '不允许' in str(e)


# ──────────────────────────────────────────
#  在线测试: 需要真实的游戏数据库
# ──────────────────────────────────────────

def test_real_data(data_dir: str):
    """用真实的雷小伊数据库跑一遍"""
    dex = Pokedex(data_dir)
    try:
        count = dex.count()
        print(f"  精灵总数: {count}")
        assert count > 0, "数据库应该有精灵数据"

        results = dex.search('雷伊')
        print(f"  搜索 '雷伊': {len(results)} 条结果")
        for r in results[:3]:
            print(f"    #{r['ID']} {r['DefName']} ({r['TypeName']})")

        fire = dex.filter_by_type('火')
        print(f"  火系精灵: {len(fire)} 条 (显示前3)")
        for r in fire[:3]:
            print(f"    #{r['ID']} {r['DefName']} ({r['TypeName']})")

        top = dex.top_n('HP', 5)
        print("  血量 Top 5:")
        for r in top:
            print(f"    #{r['ID']} {r['DefName']} HP={r['HP']}")

        # 拿第一个有属性的精灵看看克制
        if results:
            dex.print_effectiveness(results[0]['ID'])
    finally:
        dex.close()


def test_sql_injection():
    """SQL 注入防护（不需要真实数据库）"""
    dex = Pokedex('.')
    try:
        dex.top_n("1; DROP TABLE monsters;--")
        assert False, "应该抛出异常"
    except ValueError as e:
        assert '不允许' in str(e)
        print(f"  ✅ 正确拦截: {e}")


# ──────────────────────────────────────────
#  独立运行
# ──────────────────────────────────────────

_OFFLINE_TESTS = [
    test_count_excludes_skins,
    test_search,
    test_type_name_is_filled_in,
    test_filter_single_type,
    test_filter_type_includes_dual,
    test_filter_dual_type_exact,
    test_types_of,
    test_get_monster_types,
    test_type_effectiveness,
    test_get_moves,
    test_parse_move_entries,
    test_top_n,
    test_sql_injection_blocked,
    test_sql_injection,
]


if __name__ == '__main__':
    passed = 0
    for test in _OFFLINE_TESTS:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
        except Exception as e:
            print(f"  💥 {test.__name__}: {type(e).__name__}: {e}")

    print(f"\n离线测试: {passed}/{len(_OFFLINE_TESTS)} 通过")

    if len(sys.argv) > 1:
        data_dir = os.path.join(sys.argv[1], 'data')
        print(f"\n在线测试 ({data_dir}):")
        try:
            test_real_data(data_dir)
            print("  ✅ test_real_data")
        except AssertionError as e:
            print(f"  ❌ test_real_data: {e}")
        except Exception as e:
            print(f"  💥 test_real_data: {type(e).__name__}: {e}")
    else:
        print("(传入雷小伊目录可额外跑在线测试)")

    sys.exit(0 if passed == len(_OFFLINE_TESTS) else 1)
