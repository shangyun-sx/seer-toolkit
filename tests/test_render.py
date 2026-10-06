"""
测试命令行排版（cli/render.py）。

这些函数以前是 Pokedex 上的 print_* 方法 —— 想验证「表格排得对不对」就得先
建一个数据库连接。现在都是纯函数、返回字符串，断言文本即可，不用去截 stdout。

运行: python -m pytest tests/test_render.py -v
  或: python tests/test_render.py
"""

import io
import os
import sys
from contextlib import redirect_stdout

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cli import render

# 雷伊。Total 是 Pokedex._add_type_name() 补上的派生字段 —— 查询结果里
# 一定有，所以这里也带上：六维总和 = 71+108+70+101+77+105 = 532
_LEIYI = {
    'ID': 70, 'DefName': '雷伊', 'Type': 5, 'TypeName': '电',
    'HP': 71, 'Atk': 108, 'Def': 70, 'SpAtk': 101, 'SpDef': 77, 'Spd': 105,
    'Total': 532,
}

_EFFECT = {
    'name': '雷伊', 'label': '电',
    'weaknesses': [('地面', 2.0)],
    'resistances': [('飞行', 0.5)],
    'immunities': [],
}


def test_table_shows_row_and_title():
    out = render.table([_LEIYI], '搜索 雷伊')
    assert '搜索 雷伊' in out
    assert '共 1 条' in out
    assert '70' in out
    assert '雷伊' in out
    assert '电' in out
    assert '532' in out, '种族值总和没算出来'


def test_table_without_rows():
    assert '无结果' in render.table([])


def test_monster_block():
    out = render.monster(_LEIYI)
    assert '雷伊' in out
    assert '电' in out
    assert '532' in out


def test_monster_tolerates_missing_fields():
    """字段缺失时显示 '?'，不是抛 KeyError"""
    out = render.monster({'ID': 1, 'DefName': '神秘精灵'})
    assert '神秘精灵' in out


def test_effectiveness_block():
    out = render.effectiveness(_EFFECT)
    assert '雷伊' in out
    assert '弱点' in out and '地面 2x' in out
    assert '抗性' in out and '飞行 0.5x' in out
    assert '免疫' in out


def test_effectiveness_without_types():
    assert '没有可识别的属性' in render.effectiveness(None)
    assert '没有可识别的属性' in render.effectiveness({})


def test_move_list_formats_levels_and_effects():
    moves = [
        {'Name': '电光一闪', 'LearningLv': 1, 'TypeName': '电',
         'CategoryName': '物理', 'Power': 40, 'MaxPP': 30},
        {'Name': '雷神之怒', 'LearningLv': None, 'TypeName': '电',
         'CategoryName': '特殊', 'Power': 120, 'MaxPP': 5,
         'EffectText': '30%令对方麻痹'},
    ]
    out = render.move_list(moves)

    assert '电光一闪' in out
    assert 'Lv1' in out
    assert '额外' in out, '没有学习等级的技能应当显示为「额外」'
    assert '30%令对方麻痹' in out


def test_move_list_without_moves():
    assert render.move_list([]) == ''


def test_render_returns_instead_of_printing():
    """只返回字符串，不直接 print。

    否则没法断言输出 —— 测试就只能去截 stdout，那很脆。
    """
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        out = render.table([_LEIYI], 'x')
        render.monster(_LEIYI)
        render.effectiveness(_EFFECT)

    assert buffer.getvalue() == '', f'不该有 print 输出: {buffer.getvalue()!r}'
    assert isinstance(out, str)


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_table_shows_row_and_title,
        test_table_without_rows,
        test_monster_block,
        test_monster_tolerates_missing_fields,
        test_effectiveness_block,
        test_effectiveness_without_types,
        test_move_list_formats_levels_and_effects,
        test_move_list_without_moves,
        test_render_returns_instead_of_printing,
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
