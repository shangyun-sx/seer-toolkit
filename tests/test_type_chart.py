"""
测试属性克制系统。

这些测试**不需要**游戏数据库，可以离线运行。

运行: python -m pytest tests/test_type_chart.py -v
  或: python tests/test_type_chart.py
"""

import os
import sys

# Windows GBK 终端下强制 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.type_chart import (
    ELEMENT_TYPES,
    TYPE_COMBINATIONS,
    TypeChart,
    _ATTACK_RELATIONS,
)


# ──────────────────────────────────────────
#  数据完整性
# ──────────────────────────────────────────

def test_data_integrity():
    """倍率表里不能出现未知属性，倍率只能是那四个值"""
    valid_ids = set(ELEMENT_TYPES)
    assert len(valid_ids) == 26, f"应该有 26 个单属性，实际 {len(valid_ids)}"

    for attacker, targets in _ATTACK_RELATIONS.items():
        assert attacker in valid_ids, f"未知的攻击方 ID: {attacker}"
        for defender, multiple in targets.items():
            assert defender in valid_ids, f"未知的防御方 ID: {defender}"
            assert multiple in TypeChart.MULTIPLIERS, \
                f"{attacker}→{defender} 倍率 {multiple} 不在 {TypeChart.MULTIPLIERS} 中"

    # 表里必须是完整的 26 个攻击方
    assert set(_ATTACK_RELATIONS) == valid_ids


def test_name_index_roundtrip():
    """每个属性都能用中文名、英文名、ID 三种方式解析出来"""
    for type_id, (cn, en) in ELEMENT_TYPES.items():
        assert TypeChart.resolve(cn) == type_id
        assert TypeChart.resolve(en) == type_id
        assert TypeChart.resolve(en.upper()) == type_id
        assert TypeChart.resolve(type_id) == type_id
        assert TypeChart.name_of(type_id) == cn
        assert TypeChart.english_of(type_id) == en


def test_resolve_invalid():
    """无效属性应该报错，而不是静默返回 1 倍"""
    for bad in ('不存在的属性', 9999, '9999'):
        try:
            TypeChart.resolve(bad)
            assert False, f"{bad!r} 本应报错"
        except ValueError:
            pass


# ──────────────────────────────────────────
#  属性组合解析
# ──────────────────────────────────────────

def test_parse_types():
    """各种写法都要能解析成同一组 ID"""
    assert TypeChart.parse_types('火') == (3,)
    assert TypeChart.parse_types(3) == (3,)
    assert TypeChart.parse_types('fire') == (3,)
    assert TypeChart.parse_types('3') == (3,)

    # 双属性的几种写法
    for written in ('电·火', '电,火', '电，火', '电/火', '电火', ['电', '火'], [5, 3], '5,3'):
        assert TypeChart.parse_types(written) == (5, 3), f"{written!r} 解析错误"

    # 粘连写法要按最长属性名切分，不能把「圣灵」拆开
    assert TypeChart.parse_types('圣灵飞行') == (16, 4)
    assert TypeChart.parse_types('草超能') == (1, 10)

    # 去重 + 空值
    assert TypeChart.parse_types('火火') == (3,)
    assert TypeChart.parse_types('') == ()


def test_combination_table():
    """属性组合表: 138 条，单属性与 ELEMENT_TYPES 对得上"""
    assert len(TYPE_COMBINATIONS) == 138

    singles = [cid for cid, (_, _, sec) in TYPE_COMBINATIONS.items() if sec is None]
    assert len(singles) == 26, f"应该有 26 个单属性组合，实际 {len(singles)}"
    assert set(singles) == set(ELEMENT_TYPES), "单属性组合的 ID 应该和 ELEMENT_TYPES 一致"

    for cid, (name, primary, secondary) in TYPE_COMBINATIONS.items():
        assert primary in ELEMENT_TYPES, f"组合 {cid} 的第一属性 {primary} 不存在"
        if secondary is not None:
            assert secondary in ELEMENT_TYPES, f"组合 {cid} 的第二属性 {secondary} 不存在"
            assert primary != secondary, f"组合 {cid} 的两个属性相同"
            assert '·' in name


def test_expand():
    """组合 ID → 单属性 ID"""
    # 单属性
    for cid in (1, 20, 221, 222, 226):
        assert TypeChart.expand(cid) == (cid,), f"{cid} 是单属性"
    # 双属性组合
    assert TypeChart.expand(33) == (5, 3), "33 是 电·火"
    assert TypeChart.expand(21) == (1, 10), "21 是 草·超能"
    assert TypeChart.expand(100) == (16, 7), "100 是 圣灵·地面"
    # 不存在的 ID
    for bad in (0, 133, 999):
        try:
            TypeChart.expand(bad)
            assert False, f"{bad} 本应报错"
        except ValueError:
            pass


def test_parse_combination_id():
    """parse_types 也要能吃掉组合 ID，也就是数据库里存的 Type"""
    assert TypeChart.parse_types(33) == (5, 3)
    assert TypeChart.parse_types('33') == (5, 3)
    assert TypeChart.parse_types(3) == (3,)
    # 组合 ID 可以直接参与克制计算
    # 电打地面=0（无效），火打地面=1（普通）→ (0+1)/4 = 0.25
    assert TypeChart.multiplier(33, 7) == 0.25, "电·火 打 地面 = (0+1)/4"
    # 圣灵·地面 打 电·火 就是文章里的例1
    assert TypeChart.multiplier(100, 33) == 4.0, "圣灵·地面 打 电·火"


def test_label():
    """label() 把任意写法变成可读中文名"""
    assert TypeChart.label(33) == '电·火'
    assert TypeChart.label(3) == '火'
    assert TypeChart.label('fire') == '火'
    assert TypeChart.label(['电', '火']) == '电·火'
    assert TypeChart.label(100) == '圣灵·地面'


# ──────────────────────────────────────────
#  倍率计算
# ──────────────────────────────────────────

def test_single_multiplier():
    """单属性查表"""
    assert TypeChart.single('火', '草') == 2.0
    assert TypeChart.single('水', '火') == 2.0
    assert TypeChart.single('草', '火') == 0.5
    assert TypeChart.single('火', '水') == 0.5
    assert TypeChart.single('普通', '火') == 1.0
    # 无效 —— 注意方向：是「谁打谁」，不是「谁被谁打」
    assert TypeChart.single('电', '地面') == 0.0        # 电打地面无效
    assert TypeChart.single('地面', '飞行') == 0.0      # 地面打飞行无效
    assert TypeChart.single('超能', '光') == 0.0        # 超能打光无效
    assert TypeChart.single('次元', '暗影') == 0.0      # 次元打暗影无效
    assert TypeChart.single('邪灵', '神灵') == 0.0      # 邪灵打神灵无效


def test_normal_type_is_neutral():
    """普通系打谁都是 1 倍"""
    for type_id in ELEMENT_TYPES:
        assert TypeChart.multiplier('普通', type_id) == 1.0


def test_official_examples():
    """4399 文章里的权威示例"""
    # 例1: 圣灵·地面 打 电·火
    #   圣灵打电=2 地面打电=2 → f1 = 2+2 = 4
    #   圣灵打火=2 地面打火=2 → f2 = 2+2 = 4
    #   (4+4)/2 = 4
    assert TypeChart.multiplier('圣灵·地面', '电·火') == 4.0

    # 例2: 圣灵·超能 打 电·火
    #   f1 = (2+1)/2 = 1.5, f2 = (2+1)/2 = 1.5 → 1.5
    assert TypeChart.multiplier('圣灵·超能', '电·火') == 1.5

    # 单打双: 圣灵 打 电·火 → 2 和 2 都是克制 → 4
    assert TypeChart.multiplier('圣灵', '电·火') == 4.0

    # 双打单，其中一个是 0: 次元·电 打 地面 → (1+0)/4 = 0.25
    assert TypeChart.multiplier('次元·电', '地面') == 0.25

    # 双打单，普通情况: 圣灵·超能 打 电 → (2+1)/2 = 1.5
    assert TypeChart.multiplier('圣灵·超能', '电') == 1.5


def test_pair_rule_branches():
    """双属性合并的三条分支都要走到"""
    # 两个都是 2 → 4
    assert TypeChart._pair_rule(2.0, 2.0) == 4.0
    # 有一个是 0 → 求和 / 4
    assert TypeChart._pair_rule(0.0, 2.0) == 0.5
    assert TypeChart._pair_rule(1.0, 0.0) == 0.25
    # 其它 → 求和 / 2
    assert TypeChart._pair_rule(2.0, 1.0) == 1.5
    assert TypeChart._pair_rule(1.0, 1.0) == 1.0
    assert TypeChart._pair_rule(0.5, 0.5) == 0.5
    assert TypeChart._pair_rule(1.0, 0.5) == 0.75


def test_multiplier_rejects_more_than_two():
    """目前只支持双属性"""
    try:
        TypeChart.multiplier('火', '草·水·电')
        assert False, "三属性本应报错"
    except ValueError:
        pass


def test_multiplier_is_commutative_over_defender_order():
    """防守方属性顺序不影响结果"""
    assert TypeChart.multiplier('圣灵', '电·火') == TypeChart.multiplier('圣灵', '火·电')
    assert TypeChart.multiplier('圣灵·地面', '电·火') == \
        TypeChart.multiplier('圣灵·地面', '火·电')


# ──────────────────────────────────────────
#  本系加成
# ──────────────────────────────────────────

def test_stab():
    """本系加成 1.5 倍，只在技能属性与自身属性相同时生效"""
    # 电系精灵用电系技能打水系: 2 * 1.5
    assert TypeChart.with_stab('电', '电', '水') == 3.0
    # 电系精灵用火系技能打草系: 无加成
    assert TypeChart.with_stab('火', '电', '草') == 2.0
    # 双属性精灵，任一属性与技能属性相同即可
    assert TypeChart.with_stab('电', '电·火', '水') == 3.0
    assert TypeChart.with_stab('火', '电·火', '草') == 3.0
    # 电系技能打地面系（无效）→ 0 * 1.5 仍是 0
    assert TypeChart.with_stab('电', '电', '地面') == 0.0


# ──────────────────────────────────────────
#  弱点 / 抗性 / 免疫 查询
# ──────────────────────────────────────────

def test_weaknesses():
    """电·火 的 4 倍弱点是 圣灵 / 地面 / 神灵 / 自然"""
    weak = dict(TypeChart.weaknesses('电·火'))
    for name in ('圣灵', '地面', '神灵', '自然'):
        assert weak.get(name) == 4.0, f"电·火 应该 4 倍弱 {name}，实际 {weak.get(name)}"
    assert weak.get('水') == 1.5
    # 弱点列表按倍率从高到低排序
    multiples = [m for _, m in TypeChart.weaknesses('电·火')]
    assert multiples == sorted(multiples, reverse=True)


def test_immunities():
    """地面系免疫电；草系免疫光"""
    immune = dict(TypeChart.immunities('地面'))
    assert immune.get('电') == 0.0, "地面系应该免疫电系"
    assert '飞行' not in immune, "地面系并不免疫飞行"

    assert dict(TypeChart.immunities('草')).get('光') == 0.0
    assert dict(TypeChart.immunities('光')).get('超能') == 0.0
    # 电·火 没有免疫
    assert TypeChart.immunities('电·火') == []


def test_resistances():
    """草 抗 水 / 电（0.5 倍）"""
    resist = dict(TypeChart.resistances('草'))
    assert resist.get('水') == 0.5
    assert resist.get('电') == 0.5
    # 弱点里不该出现草
    assert '草' not in dict(TypeChart.weaknesses('草'))


def test_profile_covers_all_types():
    """弱点 + 抗性 + 免疫 + 普通 = 全部 26 个属性"""
    for type_id in ELEMENT_TYPES:
        profile = TypeChart.defense_profile(type_id)
        total = len(profile['weaknesses']) + len(profile['resistances']) \
            + len(profile['immunities'])
        normal = sum(
            1 for other in ELEMENT_TYPES
            if TypeChart.multiplier(other, type_id) == 1.0
        )
        assert total + normal == 26, f"属性 {type_id} 的分类不完整"


def test_offense_profile():
    """圣灵克 草/水/火/电/冰/远古，被 战斗/神秘/龙/轮回 抵抗"""
    profile = TypeChart.offense_profile('圣灵')
    strong = dict(profile['strong'])
    for name in ('草', '水', '火', '电', '冰', '远古'):
        assert strong.get(name) == 2.0, f"圣灵应该克制 {name}"
    weak = dict(profile['weak'])
    for name in ('战斗', '神秘', '龙', '轮回'):
        assert weak.get(name) == 0.5, f"圣灵应该被 {name} 抵抗"
    # 圣灵打自己是普通倍率，既不在克制里也不在微弱里
    assert '圣灵' not in strong and '圣灵' not in weak


def test_classify():
    assert TypeChart.classify(0.0) == '无效'
    assert TypeChart.classify(0.25) == '微弱'
    assert TypeChart.classify(0.5) == '微弱'
    assert TypeChart.classify(1.0) == '普通'
    assert TypeChart.classify(1.5) == '克制'
    assert TypeChart.classify(4.0) == '克制'


def test_format_profile():
    """格式化输出应该包含中文属性名和倍率"""
    text = TypeChart.format_profile('电·火')
    assert '电·火' in text
    assert '弱点' in text and '抗性' in text and '免疫' in text
    assert '圣灵4x' in text


# ──────────────────────────────────────────
#  独立运行
# ──────────────────────────────────────────

if __name__ == '__main__':
    test_list = [
        test_data_integrity,
        test_name_index_roundtrip,
        test_resolve_invalid,
        test_parse_types,
        test_combination_table,
        test_expand,
        test_parse_combination_id,
        test_label,
        test_single_multiplier,
        test_normal_type_is_neutral,
        test_official_examples,
        test_pair_rule_branches,
        test_multiplier_rejects_more_than_two,
        test_multiplier_is_commutative_over_defender_order,
        test_stab,
        test_weaknesses,
        test_immunities,
        test_resistances,
        test_profile_covers_all_types,
        test_offense_profile,
        test_classify,
        test_format_profile,
    ]
    passed = 0
    for test in test_list:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
        except Exception as e:
            print(f"  💥 {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(test_list)} 通过")
    sys.exit(0 if passed == len(test_list) else 1)
