"""
测试技能效果解析器。

离线测试用临时造的迷你 EffectInfo.db，不需要游戏数据库。
传入雷小伊目录才会跑真实数据验证。

运行: python -m pytest tests/test_effects.py -v
  或: python tests/test_effects.py                    # 只跑离线
  或: python tests/test_effects.py <雷小伊目录>         # 离线 + 真实数据
"""

import os
import sqlite3
import sys
import tempfile

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.effects import EffectParser


# ──────────────────────────────────────────
#  离线测试: 临时造一个 EffectInfo.db
# ──────────────────────────────────────────

#: 六维表（真实数据里 id 0/2/16/24 内容完全相同）
_SIX_DIM = '攻击|防御|特攻|特防|速度|命中'

#: 异常状态表，故意含空槽和 'XX' 占位（真实数据就是这样）
_STATUS = '麻痹|中毒|烧伤||寄生|冻伤|害怕|XX|睡眠'

#: 覆盖每一条推断规则的效果定义。**故意不含 id=31**，
#: 它是靠模块里的 _SUPPLEMENTAL_EFFECTS 补上的（真实数据也缺）
_FAKE_PARAM_TYPES = [
    (0, _SIX_DIM), (2, _SIX_DIM), (16, _SIX_DIM), (24, _SIX_DIM),
    (1, _STATUS),
]

_FAKE_EFFECTS = [
    # (id, argsNum, info)
    (4, 3, '技能使用成功时，{1}%改变自身{0}等级{2}'),            # 六维 + 正号
    (5, 3, '技能使用成功时，{1}%改变对手{0}等级{2}'),            # 六维（对手）
    (6, 1, '对方所受伤害的1/{0}会反弹给自己'),                    # 纯数字 + 1/{n}
    (110, 3, '{0}回合内每次躲避攻击都有{1}%概率使自身{2}提升1个等级'),  # 歧义陷阱
    (149, 4, '命中后，{0}%令对方{1}，{2}%令对方{3}'),            # 两个异常状态
    (196, 6, '{1}%令对方{0}等级{2}；若先出手，则{4}%使对方{3}等级{5}'),  # 多子句
    (35, 0, '惩罚，对方能力等级越高，此技能威力越大'),              # argsNum=0
    (900, 3, '使对手{0}种能力等级-{1}，持续{2}回合'),            # 数量词不误判
    (901, 1, '消除{0}状态'),                                     # 「状态」后缀
]


def _make_fake_effect_db(data_dir: str) -> None:
    """在 data_dir 下造一个最小的 EffectInfo.db"""
    conn = sqlite3.connect(os.path.join(data_dir, 'EffectInfo.db'))
    conn.execute('CREATE TABLE Effect (id INTEGER PRIMARY KEY, argsNum INTEGER, '
                 'info TEXT, param TEXT, analyze TEXT, key TEXT, type INTEGER)')
    conn.execute('CREATE TABLE ParamType (id INTEGER PRIMARY KEY, params TEXT, desc TEXT)')
    conn.executemany('INSERT INTO Effect (id, argsNum, info) VALUES (?,?,?)', _FAKE_EFFECTS)
    conn.executemany('INSERT INTO ParamType (id, params) VALUES (?,?)', _FAKE_PARAM_TYPES)
    conn.commit()
    conn.close()


def _with_fake_db(fn):
    """把造好库的 EffectParser 传给测试函数，结束后清理"""
    def wrapper():
        with tempfile.TemporaryDirectory() as tmp:
            _make_fake_effect_db(tmp)
            parser = EffectParser(tmp)
            try:
                fn(parser)
            finally:
                parser.close()
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ──────────────────────────────────────────
#  参数类型推断（纯函数，不碰数据库）
# ──────────────────────────────────────────

def test_infer_scheme_pure_function():
    """infer_scheme 是静态方法，可以脱离数据库单测"""
    scheme = EffectParser.infer_scheme('技能使用成功时，{1}%改变自身{0}等级{2}')
    assert scheme['0'][0] == 'stat'      # 后面紧跟「等级」
    assert scheme['1'][0] == 'num'       # % 概率
    assert scheme['2'][0] == 'num'       # 结尾
    assert scheme['2'][1] is True        # 前面是「等级」→ 是增量，要补正号
    assert scheme['1'][1] is False


def test_infer_scheme_status():
    """「令对方{n}」→ 异常状态表"""
    scheme = EffectParser.infer_scheme('命中后，{0}%令对方{1}')
    assert scheme['0'][0] == 'num'
    assert scheme['1'][0] == 'status'


def test_infer_scheme_ambiguity_trap():
    """`使自身{2}提升1个等级` 的 {2} 必须是六维，不能因为「使自身」就判成状态"""
    scheme = EffectParser.infer_scheme('{0}回合内每次躲避攻击都有{1}%概率使自身{2}提升1个等级')
    assert scheme['2'][0] == 'stat', f"应该是六维，实际 {scheme['2']}"


def test_infer_scheme_stop_words():
    """「使对手{0}种能力」里的 {0} 是数量词，不是异常状态"""
    scheme = EffectParser.infer_scheme('使对手{0}种能力等级-{1}')
    assert scheme['0'][0] == 'num', f"数量词被误判成状态: {scheme['0']}"


# ──────────────────────────────────────────
#  渲染
# ──────────────────────────────────────────

@_with_fake_db
def test_six_dim_with_sign(parser):
    """六维查表 + 正数补正号"""
    assert parser.render_effect(4, ['2', '100', '-1']) \
        == '技能使用成功时，100%改变自身特攻等级-1'
    assert parser.render_effect(4, ['0', '100', '1']) \
        == '技能使用成功时，100%改变自身攻击等级+1'


@_with_fake_db
def test_six_dim_opponent(parser):
    assert parser.render_effect(5, ['5', '15', '-1']) \
        == '技能使用成功时，15%改变对手命中等级-1'


@_with_fake_db
def test_pure_number(parser):
    assert parser.render_effect(6, ['4']) == '对方所受伤害的1/4会反弹给自己'


@_with_fake_db
def test_status_lookup(parser):
    """异常状态查表"""
    assert parser.render_effect(149, ['50', '0', '50', '1']) \
        == '命中后，50%令对方麻痹，50%令对方中毒'


@_with_fake_db
def test_status_suffix(parser):
    """「消除{n}状态」也走状态表"""
    assert parser.render_effect(901, ['2']) == '消除烧伤状态'


@_with_fake_db
def test_ambiguity_trap_rendering(parser):
    """歧义陷阱：{2} 要渲染成六维（命中），而不是异常状态名"""
    got = parser.render_effect(110, ['3', '100', '5'])
    assert got == '3回合内每次躲避攻击都有100%概率使自身命中提升1个等级', got
    # 关键: 不能出现状态名（5 号状态是「冻伤」）
    assert '冻伤' not in got


@_with_fake_db
def test_two_clause(parser):
    """一条模板里两个子句，各自查表 + 补正号"""
    assert parser.render_effect(196, ['5', '10', '-1', '5', '20', '-2']) \
        == '10%令对方命中等级-1；若先出手，则20%使对方命中等级-2'


@_with_fake_db
def test_stop_words_not_status(parser):
    """「使对手{0}种能力」的 {0} 应渲染成数字 3，不是状态名"""
    got = parser.render_effect(900, ['3', '1', '2'])
    assert got == '使对手3种能力等级-1，持续2回合', got


@_with_fake_db
def test_argsnum_zero_ignores_extra(parser):
    """argsNum=0 的效果是纯文案，多给的参数要忽略"""
    assert parser.render_effect(35, []) == '惩罚，对方能力等级越高，此技能威力越大'
    assert parser.render_effect(35, ['1', '2', '3']) \
        == '惩罚，对方能力等级越高，此技能威力越大'


# ──────────────────────────────────────────
#  多效果 / 分组
# ──────────────────────────────────────────

@_with_fake_db
def test_multi_effect_sequential(parser):
    """SideEffect 是多个效果的顺序列表，参数按各自 argsNum 依次消费"""
    texts = parser.render_move('4 5 ', '0 100 1 5 15 -1 ')
    assert texts == [
        '技能使用成功时，100%改变自身攻击等级+1',
        '技能使用成功时，15%改变对手命中等级-1',
    ], texts


@_with_fake_db
def test_repeated_same_effect(parser):
    """同一个效果重复出现"""
    texts = parser.render_move('4 4 ', '0 100 1 1 100 1 ')
    assert len(texts) == 2
    assert '攻击' in texts[0]
    assert '防御' in texts[1]


@_with_fake_db
def test_trailing_repeat(parser):
    """效果列表漏写一项时，多出来的整组继续套用最后一个效果。

    真实例子: 龙之意志 SideEffect='4 4 4 4 4'（5 个）但参数给了 6 组，
    因为六维有 6 项 —— 效果列表少写了一个 '4'。
    """
    texts = parser.render_move('4 4 4 4 4 ',
                               '0 100 1 1 100 1 2 100 1 3 100 1 4 100 1 5 100 1 ')
    assert len(texts) == 6, f"应该补出第 6 条，实际 {len(texts)} 条"
    assert '命中' in texts[5]


@_with_fake_db
def test_trailing_args_not_multiple_ignored(parser):
    """剩余参数不是整数倍时不动（真畸形），且 argsNum=0 的末尾不能误伤"""
    # 末尾效果 argsNum=0 → 多余的参数应被忽略
    texts = parser.render_move('35 ', '1 2 3 ')
    assert texts == ['惩罚，对方能力等级越高，此技能威力越大'], texts


# ──────────────────────────────────────────
#  兜底
# ──────────────────────────────────────────

@_with_fake_db
def test_supplemental_effect(parser):
    """本地库缺失、但模块里补充了定义的效果（id=31 被 303 个技能引用）"""
    assert parser.render_effect(31, ['2', '5']) == '1回合做2次攻击'


@_with_fake_db
def test_unknown_effect_fallback(parser):
    """完全不认识的效果 ID 要显示出来，不能静默吞掉、更不能抛异常"""
    texts = parser.render_move('9999 ', '1 2 ')
    assert texts == ['[未知效果#9999]'], texts


@_with_fake_db
def test_unknown_effect_mixed(parser):
    """已知 + 未知混在一起也不能崩"""
    texts = parser.render_move('4 9999 ', '0 100 1 1 2 ')
    assert len(texts) == 2
    assert '攻击等级+1' in texts[0]
    assert texts[1] == '[未知效果#9999]'


@_with_fake_db
def test_short_args_show_question_mark(parser):
    """参数不够时显示 '?'，而不是抛 IndexError"""
    got = parser.render_effect(4, ['0'])
    assert got == '技能使用成功时，?%改变自身攻击等级?', got


@_with_fake_db
def test_out_of_range_falls_back_to_number(parser):
    """六维下标越界 → 退回原始数字，不能崩"""
    assert parser.render_effect(4, ['9', '100', '1']) \
        == '技能使用成功时，100%改变自身9等级+1'


@_with_fake_db
def test_placeholder_xx_falls_back(parser):
    """状态表里的 'XX' 占位符 → 退回原始数字"""
    assert parser.render_effect(901, ['7']) == '消除7状态'


@_with_fake_db
def test_empty_side_effect(parser):
    """没有效果的技能返回空列表"""
    assert parser.render_move('', '') == []
    assert parser.render_move(None, None) == []
    assert parser.describe('', '') == ''


def test_only_numeric_placeholders():
    """占位符只认 {数字}。

    真实数据里 3546 个占位符**全部**是 {0}/{1} 这种数字形式，没有别的花样，
    所以正则只匹配数字即可；花括号里的非数字内容原样保留。
    """
    assert EffectParser.infer_scheme('消除{n}状态') == {}
    assert EffectParser.infer_scheme('{0}回合') == {'0': ('num', False)}


@_with_fake_db
def test_describe_joins(parser):
    assert parser.describe('4 5 ', '0 100 1 5 15 -1 ') == (
        '技能使用成功时，100%改变自身攻击等级+1；'
        '技能使用成功时，15%改变对手命中等级-1'
    )


def test_missing_db_raises():
    """数据库不存在时抛 FileNotFoundError（和 Pokedex 行为一致）"""
    with tempfile.TemporaryDirectory() as tmp:
        parser = EffectParser(tmp)
        try:
            parser.count()
            assert False, "应该抛 FileNotFoundError"
        except FileNotFoundError as e:
            assert 'EffectInfo.db' in str(e)


# ──────────────────────────────────────────
#  真实数据验证（需要游戏数据库）
# ──────────────────────────────────────────

#: 在真实数据上验证过的样例（即使没有 data/ 目录，离线测试也已覆盖同样的断言）
_REAL_SAMPLES = [
    (4, ['2', '100', '-1'], '技能使用成功时，100%改变自身特攻等级-1'),
    (5, ['5', '15', '-1'], '技能使用成功时，15%改变对手命中等级-1'),
    (6, ['4'], '对方所受伤害的1/4会反弹给自己'),
    (110, ['3', '100', '5'], '3回合内每次躲避攻击都有100%概率使自身命中提升1个等级'),
    (149, ['50', '0', '50', '1'], '命中后，50%令对方麻痹，50%令对方中毒'),
    (196, ['5', '10', '-1', '5', '20', '-2'],
     '10%令对方命中等级-1；若先出手，则20%使对方命中等级-2'),
    (31, ['2', '5'], '1回合做2次攻击'),
]


def check_real_data(data_dir: str):
    """用真实的 EffectInfo.db / Moves.db 全量渲染。

    只断言「不崩 + 覆盖率」，不写死具体字符串 —— 数据库版本升级时
    文案可能微调，写死会变成假失败。

    故意不叫 test_* —— 它需要外部数据目录，pytest 收集到会报
    「fixture 'data_dir' not found」。用 `python tests/test_effects.py <目录>` 跑。
    """
    parser = EffectParser(data_dir)
    try:
        assert parser.count() > 2000, f"效果表太小: {parser.count()}"

        print(f"  效果总数: {parser.count()}")
        for effect_id, args, expected in _REAL_SAMPLES:
            got = parser.render_effect(effect_id, args)
            assert got == expected, f"eff{effect_id}: {got!r} != {expected!r}"
        print(f"  {len(_REAL_SAMPLES)} 条权威样例全部一致")

        moves_db = os.path.join(os.path.dirname(data_dir), 'data', 'Moves.db')
        if not os.path.exists(moves_db):
            moves_db = os.path.join(data_dir, 'Moves.db')
        conn = sqlite3.connect(moves_db)
        conn.row_factory = sqlite3.Row

        total = rendered = failed = 0
        for row in conn.execute(
                "SELECT SideEffect, SideEffectArg FROM moves WHERE SideEffect!=''"):
            total += 1
            try:
                if parser.render_move(row['SideEffect'], row['SideEffectArg']):
                    rendered += 1
            except Exception as e:      # noqa: BLE001 - 这里就是要抓所有异常
                failed += 1
                if failed <= 3:
                    print(f"    ❌ {row['SideEffect']} / {row['SideEffectArg']}: {e}")
        conn.close()

        rate = rendered / total * 100 if total else 0
        print(f"  全量渲染 {total} 个技能: 成功 {rendered} ({rate:.2f}%), 异常 {failed}")
        assert failed == 0, f"有 {failed} 个技能渲染时抛异常"
        assert total > 20000, f"技能数太少，可能不是完整的数据库: {total}"
        assert rate >= 99.0, f"渲染覆盖率过低: {rate:.2f}%"
    finally:
        parser.close()


# ──────────────────────────────────────────
#  独立运行
# ──────────────────────────────────────────

_OFFLINE_TESTS = [
    test_infer_scheme_pure_function,
    test_infer_scheme_status,
    test_infer_scheme_ambiguity_trap,
    test_infer_scheme_stop_words,
    test_six_dim_with_sign,
    test_six_dim_opponent,
    test_pure_number,
    test_status_lookup,
    test_status_suffix,
    test_ambiguity_trap_rendering,
    test_two_clause,
    test_stop_words_not_status,
    test_argsnum_zero_ignores_extra,
    test_multi_effect_sequential,
    test_repeated_same_effect,
    test_trailing_repeat,
    test_trailing_args_not_multiple_ignored,
    test_supplemental_effect,
    test_unknown_effect_fallback,
    test_unknown_effect_mixed,
    test_short_args_show_question_mark,
    test_out_of_range_falls_back_to_number,
    test_placeholder_xx_falls_back,
    test_empty_side_effect,
    test_only_numeric_placeholders,
    test_describe_joins,
    test_missing_db_raises,
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
        print(f"\n真实数据验证 ({data_dir}):")
        try:
            check_real_data(data_dir)
            print("  ✅ check_real_data")
        except AssertionError as e:
            print(f"  ❌ check_real_data: {e}")
        except Exception as e:
            print(f"  💥 check_real_data: {type(e).__name__}: {e}")
    else:
        print("(传入雷小伊目录可额外跑真实数据验证)")

    sys.exit(0 if passed == len(_OFFLINE_TESTS) else 1)
