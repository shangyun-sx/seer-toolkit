"""
对真实游戏数据做的检查 —— 有真表就跑，没有就跳过。
==================================================

真表（雷小伊的 data/*.db）不在仓库里（.gitignore 排除）。所以这里用 `skipif`
而不是"标记为不进 CI"：

  * CI 上真表自然不存在，整个文件自动跳过，**CI 配置一个字都不用改**
  * 哪天真表被缓存进 CI，它会自动生效 —— 不依赖谁记得去改配置

**什么时候该跑**：每次游戏更新、换上新的 data/ 之后。见 README 的「数据更新」
一节。别指望"想起来就跑"——那条路没人走得通。

--------------------------------------------------------------------------

这里查的是**两件不同的事，故意分成两组、不合并**：

  1. schema 快照 —— 真表的列还在不在（列名/类型层面）
  2. 域值断言 —— 列的**含义**还是不是代码假设的那个

失效模式完全不同：列没了是运行时 `no such column`（响亮），而含义变了是
**静默出错** —— 列名没变、类型没变，只是数据换了意思，代码照跑不误、结果全错。

合并成一个 check 的话，红了只知道「游戏数据变了」，不知道动哪儿。

--------------------------------------------------------------------------

**故意不查的一条**（写在这里，免得将来有人重新推一遍）：

`_NOT_SKIN = 'ID < 15000'`（database/pokedex.py）把 ID >= 15000 当皮肤排除。
这是对游戏数据的假设，但这里**不做自动检查**，因为断言不出来：

  * 实测 min(ID >= 15000) = 15001，恰好卡在阈值上 —— 看着确实像边界
  * 但"恰好从 15001 开始"太脆：游戏哪天给别的东西分配 ID 15000，检查就误报，
    而实际什么都没坏
  * 换粗一点的写法（"ID >= 15000 的行数落在某个区间"）又挡不住真正有意义的变化

与其写一条会误报、然后让人学会忽略它的检查，不如明说这条没查。将来真要做，
先想清楚：**什么变化才算"游戏改了这个约定"的可靠信号**。
"""

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.type_chart import TYPE_COMBINATIONS   # noqa: E402

DATA_DIR = Path(__file__).parent.parent / 'data'

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / 'Monster.db').exists(),
    reason='没有真实游戏数据（仓库里不含 data/）—— 见本文件开头的说明',
)

#: 代码实际读的列。任何一列在真表里没了，运行时就 `no such column`。
#: 来源：database/pokedex.py 里那几条 SELECT。
REQUIRED_MONSTER_COLUMNS = {'ID', 'DefName', 'Type', 'HP', 'Atk', 'Def',
                            'SpAtk', 'SpDef', 'Spd', 'Moves'}
REQUIRED_MOVES_COLUMNS = {'ID', 'Name', 'Type', 'Category', 'Power', 'MaxPP',
                          'Accuracy', 'SideEffect', 'SideEffectArg'}

#: Moves.Category 的取值。database/pokedex.py 的 _MOVE_CATEGORY_CN 只认这三个。
KNOWN_CATEGORIES = {1, 2, 4}


def _columns(db_path: Path, table: str) -> set:
    conn = sqlite3.connect(db_path)
    try:
        # PRAGMA 不支持参数绑定，表名只能拼 —— 这里的表名都是本文件写死的常量
        return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    finally:
        conn.close()


# ──────────────────────────────────────────
#  第一组：schema —— 列还在不在
# ──────────────────────────────────────────

def test_real_monster_schema_covers_what_the_code_reads():
    """真表缺了代码要读的列 → 运行时 no such column"""
    missing = REQUIRED_MONSTER_COLUMNS - _columns(DATA_DIR / 'Monster.db', 'monsters')

    assert not missing, (
        f'真表 monsters 少了代码要用的列: {sorted(missing)}\n'
        '—— 注意：**第一动作不是更新这份清单**，而是先看离线测试的假表\n'
        '   （tests/test_pokedex.py 的 _make_fake_db）要不要跟着改。\n'
        '   假表不跟着改的话，离线测试会继续绿，但测的已经不是真表了。'
    )


def test_real_moves_schema_covers_what_the_code_reads():
    missing = REQUIRED_MOVES_COLUMNS - _columns(DATA_DIR / 'Moves.db', 'moves')

    assert not missing, (
        f'真表 moves 少了代码要用的列: {sorted(missing)}\n'
        '（同上：先看 tests 里的假表要不要一起改）'
    )


# ──────────────────────────────────────────
#  第二组：域值 —— 列的含义还是不是代码假设的那个
# ──────────────────────────────────────────

def test_move_categories_are_the_ones_the_code_knows():
    """_MOVE_CATEGORY_CN 只认 1=物理 / 2=特殊 / 4=属性。

    多出别的取值时界面不会崩（代码会用 str 兜底显示数字），但那意味着
    "技能类别" 这一栏从中文悄悄降级成了数字 —— 正是要抓的静默失效。
    """
    conn = sqlite3.connect(DATA_DIR / 'Moves.db')
    try:
        actual = {row[0] for row in conn.execute('SELECT DISTINCT Category FROM moves')}
    finally:
        conn.close()

    unexpected = actual - KNOWN_CATEGORIES
    assert not unexpected, (
        f'Moves.Category 出现了代码不认识的取值: {sorted(unexpected)}\n'
        f'  代码认识的只有: {sorted(KNOWN_CATEGORIES)}\n'
        '  → 界面会把这几个类别显示成数字（代码有兜底，不会崩，但也不对）\n'
        '  → 要改的是 pokedex.py 的 _MOVE_CATEGORY_CN'
    )


def test_monster_types_are_known_combinations():
    """monsters.Type 存的是属性组合 ID，属性克制全靠它查表。

    出现不认识的值 → 这只精灵的属性克制会算错（或者显示成原始数字）。
    0 要放行：那是载具/道具形态，本来就没有属性，代码用 try/except 兜底。
    """
    conn = sqlite3.connect(DATA_DIR / 'Monster.db')
    try:
        actual = {row[0] for row in conn.execute('SELECT DISTINCT Type FROM monsters')}
    finally:
        conn.close()

    unknown = actual - set(TYPE_COMBINATIONS) - {0}
    assert not unknown, (
        f'monsters.Type 出现了 TYPE_COMBINATIONS 里没有的取值: {sorted(unknown)}\n'
        '  → 这些精灵的属性克制会算错\n'
        '  → 要改的是 database/type_chart.py 的 TYPE_COMBINATIONS'
    )


def test_effect_placeholders_fit_arg_counts():
    """effects.py 依赖一个实测出来的不变式：模板里任何 {n} 都 < argsNum。

    破了不会崩 —— render_effect 用 '?' 兜底 —— 但技能描述会变成
    "攻击等级?" 这种半截话。
    """
    conn = sqlite3.connect(DATA_DIR / 'EffectInfo.db')
    try:
        broken = []
        for effect_id, args_num, info in conn.execute(
                'SELECT id, argsNum, info FROM Effect'):
            if not info:
                continue
            for slot in re.findall(r'\{(\d+)\}', info):
                if int(slot) >= (args_num or 0):
                    broken.append((effect_id, int(slot), args_num))
                    break
    finally:
        conn.close()

    assert not broken, (
        f'有 {len(broken)} 条效果的模板引用了超出 argsNum 的参数（前几条）: {broken[:5]}\n'
        '  → 技能描述里那几处会显示成 "?"\n'
        '  → effects.py 顶部的说明是按这个不变式写的，要和真实数据对齐'
    )


if __name__ == '__main__':
    # 不使用 pytest 也能跑（但它要 pytest 的 skipif 语义，所以只做个提示）
    if not (DATA_DIR / 'Monster.db').exists():
        print(f'  跳过：没有真实游戏数据（{DATA_DIR}）')
        sys.exit(0)
    print('  这个文件请用 pytest 跑：python -m pytest tests/test_real_data.py -v')
    sys.exit(0)
