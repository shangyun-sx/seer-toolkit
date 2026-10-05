"""
属性克制系统 —— 借鉴 SeerAPI 的属性建模
=======================================

SeerAPI (github.com/SeerAPI/seerapi) 把属性拆成三个概念：

    * ElementType          单个属性（中文名 + 英文名）
    * ElementTypeRelation  单属性之间的克制倍率
    * TypeCombination      单/双属性组合，双属性倍率「由公式计算得出」

本模块用同样的思路实现赛尔号的属性克制，不依赖游戏数据库：

    * ELEMENT_TYPES        26 个单属性
    * _ATTACK_RELATIONS    攻击方 → 防御方 的倍率表（只存 != 1.0 的项）
    * TypeChart            把倍率表算成单/双属性之间的最终克制系数

倍率只有 {0, 0.5, 1, 2} 四种取值。双属性**不能**简单地把两个单属性倍率相乘，
赛尔号用的是「拆分后求和再修正」的规则：

    单打单          直接查表
    单打双 / 双打单  拆开双属性得到 x1、x2：
                        x1 == x2 == 2        → 4
                        x1 == 0 或 x2 == 0   → (x1 + x2) / 4
                        其它                 → (x1 + x2) / 2
    双打双          先算「双属性打单属性」的两个结果 f1、f2，再 (f1 + f2) / 2
                    （拆的是**防守方**的两个属性，不是攻击方）

举例：圣灵·地面 打 电·火 → f1 = 2+2 = 4，f2 = 2+2 = 4 → (4+4)/2 = 4
      圣灵·超能 打 电·火 → f1 = (2+1)/2 = 1.5，f2 = 1.5 → 1.5
      次元·电   打 地面   → (1+0)/4 = 0.25

数据来源: https://api.seerapi.com/v1/element_type/<id>
公式来源: 4399《单双属性克制系数计算方法与n属性计算公式猜想》
"""

import re
from typing import Dict, List, Optional, Sequence, Tuple, Union

# 属性名 / 属性 ID / 属性组合，都可以作为参数传入
TypeLike = Union[str, int, Sequence[Union[str, int]]]

# ──────────────────────────────────────────
#  数据表
# ──────────────────────────────────────────

#: 属性 ID → (中文名, 英文名)
ELEMENT_TYPES: Dict[int, Tuple[str, str]] = {
    1: ("草", "grass"),
    2: ("水", "water"),
    3: ("火", "fire"),
    4: ("飞行", "flying"),
    5: ("电", "electric"),
    6: ("机械", "steel"),
    7: ("地面", "ground"),
    8: ("普通", "normal"),
    9: ("冰", "ice"),
    10: ("超能", "psychic"),
    11: ("战斗", "fight"),
    12: ("光", "light"),
    13: ("暗影", "dark"),
    14: ("神秘", "myth"),
    15: ("龙", "dragon"),
    16: ("圣灵", "saint"),
    17: ("次元", "dimension"),
    18: ("远古", "ancient"),
    19: ("邪灵", "demon"),
    20: ("自然", "nature"),
    221: ("王", "king"),
    222: ("混沌", "chaos"),
    223: ("神灵", "deity"),
    224: ("轮回", "samsara"),
    225: ("虫", "insect"),
    226: ("虚空", "void"),
}

#: 攻击方 ID → {防御方 ID: 倍率}，只收录倍率 != 1.0 的项（缺省即 1.0）
_ATTACK_RELATIONS: Dict[int, Dict[int, float]] = {
    1: {1: 0.5, 2: 2, 3: 0.5, 4: 0.5, 6: 0.5, 7: 2, 12: 2, 16: 0.5, 18: 0.5, 222: 0.5, 223: 0.5},
    2: {1: 0.5, 2: 0.5, 3: 2, 7: 2, 16: 0.5, 20: 0.5, 222: 0.5, 223: 0.5},
    3: {1: 2, 2: 0.5, 3: 0.5, 6: 2, 9: 2, 16: 0.5, 20: 0.5, 222: 0.5, 223: 0.5},
    4: {1: 2, 5: 0.5, 6: 0.5, 11: 2, 17: 0.5, 19: 0.5, 20: 0.5, 222: 0.5, 225: 2},
    5: {1: 0.5, 2: 2, 4: 2, 5: 0.5, 7: 0, 13: 2, 14: 0.5, 16: 0.5, 17: 2, 20: 0.5, 222: 2, 223: 0.5, 226: 2},
    6: {2: 0.5, 3: 0.5, 5: 0.5, 6: 0.5, 9: 2, 11: 2, 17: 0.5, 18: 2, 19: 2, 223: 2},
    7: {1: 0.5, 3: 2, 4: 0, 5: 2, 6: 2, 10: 0.5, 13: 0.5, 15: 0.5, 16: 0.5, 20: 0.5, 221: 2, 223: 0.5, 224: 2, 225: 0.5},
    8: {},
    9: {1: 2, 2: 0.5, 3: 0.5, 4: 2, 6: 0.5, 7: 2, 9: 0.5, 16: 0.5, 17: 2, 18: 2, 222: 0.5, 223: 0.5, 224: 2, 225: 2},
    10: {6: 0.5, 10: 0.5, 11: 2, 12: 0, 14: 2, 20: 2, 225: 0.5},
    11: {6: 2, 9: 2, 10: 0.5, 11: 0.5, 13: 0.5, 15: 2, 16: 2, 19: 0.5, 221: 0.5},
    12: {1: 0, 6: 0.5, 9: 0.5, 10: 2, 12: 0.5, 13: 2, 16: 0.5, 19: 0.5, 20: 0.5, 223: 0.5, 224: 0.5, 225: 2, 226: 0.5},
    13: {6: 0.5, 9: 0.5, 10: 2, 12: 0.5, 13: 2, 16: 0.5, 17: 2, 19: 0.5, 223: 0.5},
    14: {5: 2, 7: 0.5, 11: 0.5, 14: 2, 16: 2, 19: 0.5, 20: 2, 221: 2, 222: 0.5, 223: 2, 224: 2, 225: 0.5},
    15: {1: 0.5, 2: 0.5, 3: 0.5, 5: 0.5, 9: 2, 15: 2, 16: 2, 18: 0.5, 19: 2, 225: 0.5},
    16: {1: 2, 2: 2, 3: 2, 5: 2, 9: 2, 11: 0.5, 14: 0.5, 15: 0.5, 18: 2, 224: 0.5, 226: 2},
    17: {4: 2, 6: 2, 9: 0.5, 10: 2, 13: 0, 19: 2, 20: 2, 221: 0.5, 222: 0.5, 223: 0.5, 224: 0.5, 225: 2, 226: 2},
    18: {1: 2, 4: 2, 6: 0.5, 9: 0.5, 14: 2, 15: 2, 221: 0.5, 224: 0.5, 226: 2},
    19: {6: 0.5, 9: 0.5, 10: 0.5, 12: 2, 13: 2, 14: 2, 16: 0.5, 17: 2, 20: 2, 221: 0.5, 222: 0.5, 223: 0, 224: 0.5},
    20: {1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 0.5, 7: 2, 10: 0.5, 11: 0.5, 12: 2, 13: 0.5, 14: 0.5, 17: 0.5, 19: 0.5, 221: 2, 222: 0.5, 224: 2, 226: 0.5},
    221: {10: 0.5, 11: 2, 13: 2, 17: 2, 19: 2, 20: 0.5, 225: 0.5},
    222: {4: 2, 5: 0.5, 6: 0.5, 9: 2, 11: 0.5, 14: 2, 17: 2, 19: 2, 20: 2, 223: 2, 224: 0.5, 226: 0},
    223: {1: 2, 2: 2, 3: 2, 5: 2, 6: 0.5, 9: 2, 11: 0.5, 15: 0.5, 18: 2, 19: 2, 222: 2},
    224: {9: 0.5, 10: 0.5, 12: 2, 13: 2, 16: 2, 17: 2, 19: 2, 20: 0.5, 222: 2, 226: 0.5},
    225: {1: 2, 2: 0.5, 3: 0.5, 7: 2, 9: 0.5, 11: 2, 12: 0.5, 222: 2, 225: 2},
    226: {4: 0.5, 10: 2, 11: 2, 12: 2, 13: 0.5, 14: 2, 16: 0.5, 17: 0.5, 20: 2, 224: 2},
}


#: 属性组合 ID → (名称, 第一属性 ID, 第二属性 ID)
#:
#: 赛尔号的属性组合自成一个 ID 空间，和单属性 ID **不重叠**：
#:     1 ~ 20    → 单属性（与 ELEMENT_TYPES 的 1~20 一致）
#:     21 ~ 132  → 双属性组合
#:     221 ~ 226 → 单属性（王 / 混沌 / 神灵 / 轮回 / 虫 / 虚空）
#: 所以数据库里存的数字 Type 如果是 21~132，就说明是双属性精灵。
TYPE_COMBINATIONS: Dict[int, Tuple[str, int, Optional[int]]] = {
    1: ("草", 1, None),
    2: ("水", 2, None),
    3: ("火", 3, None),
    4: ("飞行", 4, None),
    5: ("电", 5, None),
    6: ("机械", 6, None),
    7: ("地面", 7, None),
    8: ("普通", 8, None),
    9: ("冰", 9, None),
    10: ("超能", 10, None),
    11: ("战斗", 11, None),
    12: ("光", 12, None),
    13: ("暗影", 13, None),
    14: ("神秘", 14, None),
    15: ("龙", 15, None),
    16: ("圣灵", 16, None),
    17: ("次元", 17, None),
    18: ("远古", 18, None),
    19: ("邪灵", 19, None),
    20: ("自然", 20, None),
    21: ("草·超能", 1, 10),
    22: ("草·战斗", 1, 11),
    23: ("草·暗影", 1, 13),
    24: ("水·超能", 2, 10),
    25: ("水·暗影", 2, 13),
    26: ("水·龙", 2, 15),
    27: ("火·飞行", 3, 4),
    28: ("火·龙", 3, 15),
    29: ("火·超能", 3, 10),
    30: ("飞行·超能", 4, 10),
    31: ("光·飞行", 12, 4),
    32: ("飞行·龙", 4, 15),
    33: ("电·火", 5, 3),
    34: ("电·冰", 5, 9),
    35: ("电·战斗", 5, 11),
    36: ("暗影·电", 13, 5),
    37: ("机械·地面", 6, 7),
    38: ("机械·超能", 6, 10),
    39: ("机械·龙", 6, 15),
    40: ("地面·龙", 7, 15),
    41: ("战斗·地面", 11, 7),
    42: ("地面·暗影", 7, 13),
    43: ("冰·龙", 9, 15),
    44: ("冰·光", 9, 12),
    45: ("冰·暗影", 9, 13),
    46: ("超能·冰", 10, 9),
    47: ("战斗·火", 11, 3),
    48: ("战斗·暗影", 11, 13),
    49: ("光·神秘", 12, 14),
    50: ("暗影·神秘", 13, 14),
    51: ("神秘·超能", 14, 10),
    52: ("圣灵·光", 16, 12),
    53: ("飞行·神秘", 4, 14),
    54: ("地面·超能", 7, 10),
    55: ("暗影·龙", 13, 15),
    56: ("圣灵·暗影", 16, 13),
    57: ("远古·战斗", 18, 11),
    58: ("火·神秘", 3, 14),
    59: ("光·战斗", 12, 11),
    60: ("神秘·战斗", 14, 11),
    61: ("次元·战斗", 17, 11),
    62: ("邪灵·神秘", 19, 14),
    63: ("远古·龙", 18, 15),
    64: ("光·次元", 12, 17),
    65: ("远古·圣灵", 18, 16),
    66: ("水·战斗", 2, 11),
    67: ("电·龙", 5, 15),
    68: ("光·火", 12, 3),
    69: ("光·暗影", 12, 13),
    70: ("邪灵·龙", 19, 15),
    71: ("远古·神秘", 18, 14),
    72: ("机械·次元", 6, 17),
    73: ("战斗·龙", 11, 15),
    74: ("战斗·自然", 11, 20),
    75: ("邪灵·机械", 19, 6),
    76: ("电·次元", 5, 17),
    77: ("远古·火", 18, 3),
    78: ("圣灵·战斗", 16, 11),
    79: ("圣灵·次元", 16, 17),
    80: ("圣灵·电", 16, 5),
    81: ("远古·地面", 18, 7),
    82: ("远古·草", 18, 1),
    83: ("自然·龙", 20, 15),
    84: ("冰·神秘", 9, 14),
    85: ("飞行·暗影", 4, 13),
    86: ("冰·火", 9, 3),
    87: ("冰·飞行", 9, 4),
    88: ("自然·圣灵", 20, 16),
    89: ("混沌·圣灵", 222, 16),
    90: ("远古·邪灵", 18, 19),
    91: ("自然·冰", 20, 9),
    92: ("混沌·暗影", 222, 13),
    93: ("混沌·战斗", 222, 11),
    94: ("混沌·超能", 222, 10),
    95: ("圣灵·超能", 16, 10),
    96: ("混沌·地面", 222, 7),
    97: ("暗影·邪灵", 13, 19),
    98: ("混沌·远古", 222, 18),
    99: ("混沌·邪灵", 222, 19),
    100: ("圣灵·地面", 16, 7),
    101: ("火·暗影", 3, 13),
    102: ("光·超能", 12, 10),
    103: ("机械·战斗", 6, 11),
    104: ("飞行·电", 4, 5),
    105: ("混沌·飞行", 222, 4),
    106: ("混沌·龙", 222, 15),
    107: ("混沌·火", 222, 3),
    108: ("圣灵·火", 16, 3),
    109: ("地面·神秘", 7, 14),
    110: ("混沌·次元", 222, 17),
    111: ("混沌·冰", 222, 9),
    112: ("自然·神秘", 20, 14),
    113: ("虚空·邪灵", 226, 19),
    114: ("虚空·混沌", 226, 222),
    115: ("圣灵·轮回", 16, 224),
    116: ("水·次元", 2, 17),
    117: ("圣灵·神秘", 16, 14),
    118: ("机械·神秘", 6, 14),
    119: ("水·神秘", 2, 14),
    120: ("次元·龙", 17, 15),
    121: ("自然·超能", 20, 10),
    122: ("电·机械", 5, 6),
    123: ("神秘·轮回", 14, 224),
    124: ("水·机械", 2, 6),
    125: ("火·机械", 3, 6),
    126: ("草·机械", 1, 6),
    127: ("远古·电", 18, 5),
    128: ("圣灵·飞行", 16, 4),
    129: ("远古·机械", 18, 6),
    130: ("远古·光", 18, 12),
    131: ("混沌·光", 222, 12),
    132: ("火·虫", 3, 225),
    221: ("王", 221, None),
    222: ("混沌", 222, None),
    223: ("神灵", 223, None),
    224: ("轮回", 224, None),
    225: ("虫", 225, None),
    226: ("虚空", 226, None),
}

#: 属性组合里出现过的分隔符
_SEPARATORS = ("·", "・", ",", "，", "/", "|", "+", " ")
_SPLIT_RE = re.compile("|".join(re.escape(s) for s in _SEPARATORS))


def _build_name_index() -> Dict[str, int]:
    """中文名 / 英文名 → ID 的查找表"""
    index: Dict[str, int] = {}
    for type_id, (cn, en) in ELEMENT_TYPES.items():
        index[cn] = type_id
        index[en] = type_id
        index[en.upper()] = type_id
    return index


_NAME_TO_ID = _build_name_index()

#: 按长度倒序的属性名，用于把「火飞行」这类粘连写法切开
_NAMES_BY_LENGTH = sorted(_NAME_TO_ID, key=len, reverse=True)


class TypeChart:
    """赛尔号属性克制计算器。

    所有方法都接受「属性名」「属性 ID」或它们的组合：

        TypeChart.multiplier('火', '草')          # 2.0
        TypeChart.multiplier('圣灵', '电·火')     # 4.0
        TypeChart.multiplier(['圣灵', '超能'], '电·火')  # 1.5
        TypeChart.defense_profile('电·火')
    """

    #: 本系加成：技能属性与自身属性相同时额外乘的倍率
    STAB = 1.5

    #: 单属性之间可能出现的全部倍率
    MULTIPLIERS = (0.0, 0.5, 1.0, 2.0)

    # ──────────────────────────────────────────
    #  属性名 / ID 解析
    # ──────────────────────────────────────────

    @staticmethod
    def resolve(value: Union[str, int]) -> int:
        """把属性名或单属性 ID 统一成**单属性** ID"""
        if isinstance(value, bool):
            raise TypeError(f"无法识别的属性: {value!r}")
        if isinstance(value, int):
            if value in ELEMENT_TYPES:
                return value
            raise ValueError(f"未知属性 ID: {value}")

        text = str(value).strip()
        if text in _NAME_TO_ID:
            return _NAME_TO_ID[text]
        if text.upper() in _NAME_TO_ID:
            return _NAME_TO_ID[text.upper()]
        if text.isdigit() and int(text) in ELEMENT_TYPES:
            return int(text)
        raise ValueError(f"无法识别的属性: {value!r}")

    @staticmethod
    def expand(type_id: int) -> Tuple[int, ...]:
        """属性组合 ID → 单属性 ID 元组。

        1~20 / 221~226 是单属性，返回 1 个；
        21~132 是双属性组合，返回 2 个。
        """
        if type_id in ELEMENT_TYPES:
            return (type_id,)
        combo = TYPE_COMBINATIONS.get(type_id)
        if combo is not None:
            _, primary, secondary = combo
            return (primary,) if secondary is None else (primary, secondary)
        raise ValueError(f"未知属性 ID: {type_id}")

    @staticmethod
    def _resolve_token(text: str) -> Tuple[int, ...]:
        """解析单个 token：可能是组合 ID、单属性 ID 或属性名"""
        if text.isdigit():
            return TypeChart.expand(int(text))
        type_id = _NAME_TO_ID.get(text) or _NAME_TO_ID.get(text.upper())
        if type_id is not None:
            return (type_id,)
        raise ValueError(f"无法识别的属性: {text!r}")

    @staticmethod
    def parse_types(value: TypeLike) -> Tuple[int, ...]:
        """把任意写法解析成**单属性** ID 元组（去重、保持顺序）。

        支持: 3 / '3' / '火' / 'fire' / '火,3' / '火·飞行' / '火飞行' / [3, 4]

        也支持属性组合 ID: parse_types(33) → (5, 3)，因为 33 是「电·火」。
        """
        if isinstance(value, (list, tuple)):
            ids: List[int] = []
            for item in value:
                ids.extend(TypeChart.parse_types(item))
            return tuple(dict.fromkeys(ids))
        if isinstance(value, int) and not isinstance(value, bool):
            return TypeChart.expand(value)

        text = str(value).strip()
        if not text:
            return ()

        # 显式分隔符: "3,2" / "火·飞行"
        parts = [p for p in _SPLIT_RE.split(text) if p]
        if len(parts) > 1:
            ids = []
            for part in parts:
                ids.extend(TypeChart._resolve_token(part))
            return tuple(dict.fromkeys(ids))

        try:
            return TypeChart._resolve_token(text)
        except ValueError:
            pass

        # 粘连写法: "火飞行" → 火 + 飞行（贪心最长匹配）
        ids = []
        i = 0
        while i < len(text):
            for name in _NAMES_BY_LENGTH:
                if text.startswith(name, i):
                    ids.append(_NAME_TO_ID[name])
                    i += len(name)
                    break
            else:
                raise ValueError(f"无法解析属性组合: {text!r}")
        return tuple(dict.fromkeys(ids))

    @staticmethod
    def label(value: TypeLike) -> str:
        """任意属性写法 → 显示用中文名（双属性用 · 连接）"""
        return "·".join(ELEMENT_TYPES[i][0] for i in TypeChart.parse_types(value))

    @staticmethod
    def name_of(value: Union[str, int]) -> str:
        """单属性 ID / 名称 → 中文名"""
        return ELEMENT_TYPES[TypeChart.resolve(value)][0]

    @staticmethod
    def english_of(value: Union[str, int]) -> str:
        """属性 ID / 名称 → 英文名"""
        return ELEMENT_TYPES[TypeChart.resolve(value)][1]

    @staticmethod
    def all_types() -> List[Tuple[int, str, str]]:
        """全部单属性: [(ID, 中文名, 英文名), ...]"""
        return [(tid, cn, en) for tid, (cn, en) in ELEMENT_TYPES.items()]

    @staticmethod
    def combination_ids(types: TypeLike) -> List[int]:
        """找出「属性组合 ID」的候选集合，用于按属性筛选精灵。

        数据库里精灵的属性存的是属性组合 ID，双属性精灵的属性是一个
        21~132 的组合 ID。所以想筛「火系」精灵，不能只找 3，还要把
        所有含火的组合（火·飞行、火·龙……）都算上。

            TypeChart.combination_ids('火')      # [3, 27, 28, ..., 132]
            TypeChart.combination_ids('电·火')   # [33]  —— 双属性时精确匹配
        """
        wanted = set(TypeChart.parse_types(types))
        if not wanted:
            return []

        result = []
        for combo_id, (_, primary, secondary) in TYPE_COMBINATIONS.items():
            members = {primary} if secondary is None else {primary, secondary}
            if len(wanted) == 1:
                if wanted <= members:
                    result.append(combo_id)
            elif members == wanted:
                result.append(combo_id)
        return result

    # ──────────────────────────────────────────
    #  倍率计算
    # ──────────────────────────────────────────

    @staticmethod
    def single(attack: Union[str, int], defense: Union[str, int]) -> float:
        """单属性打单属性的倍率（查表）"""
        atk = TypeChart.parse_types(attack)
        dfd = TypeChart.parse_types(defense)
        if len(atk) != 1 or len(dfd) != 1:
            raise ValueError("single() 只接受单属性，双属性请用 multiplier()")
        return _ATTACK_RELATIONS.get(atk[0], {}).get(dfd[0], 1.0)

    @staticmethod
    def _pair_rule(x1: float, x2: float) -> float:
        """单打双 / 双打单 的合并规则"""
        if x1 == 2.0 and x2 == 2.0:
            return 4.0
        if x1 == 0.0 or x2 == 0.0:
            return (x1 + x2) / 4.0
        return (x1 + x2) / 2.0

    @staticmethod
    def multiplier(attack: TypeLike, defense: TypeLike) -> float:
        """攻击方打防守方的最终克制系数（双方各支持最多 2 个属性）"""
        atk = TypeChart.parse_types(attack)
        dfd = TypeChart.parse_types(defense)
        if not atk or not dfd:
            raise ValueError("攻击方和防守方都必须至少有一个属性")
        if len(atk) > 2 or len(dfd) > 2:
            raise ValueError("最多只支持双属性")

        def raw(a: int, d: int) -> float:
            return _ATTACK_RELATIONS.get(a, {}).get(d, 1.0)

        if len(atk) == 1 and len(dfd) == 1:
            return raw(atk[0], dfd[0])
        if len(atk) == 2 and len(dfd) == 1:
            return TypeChart._pair_rule(raw(atk[0], dfd[0]), raw(atk[1], dfd[0]))
        if len(atk) == 1 and len(dfd) == 2:
            return TypeChart._pair_rule(raw(atk[0], dfd[0]), raw(atk[0], dfd[1]))
        # 双打双：拆防守方的两个属性，各算一次「双打单」，再取平均
        f1 = TypeChart._pair_rule(raw(atk[0], dfd[0]), raw(atk[1], dfd[0]))
        f2 = TypeChart._pair_rule(raw(atk[0], dfd[1]), raw(atk[1], dfd[1]))
        return (f1 + f2) / 2.0

    @staticmethod
    def with_stab(skill_type: Union[str, int], attacker: TypeLike,
                  defender: TypeLike) -> float:
        """技能命中防守方的最终倍率（含本系加成）

        skill_type  技能属性
        attacker    使用者的属性 —— 用于判断是否触发本系加成
        defender    防守方的属性

        例: 电系精灵用火系技能打草系 → 2.0（无加成）
            电系精灵用电系技能打草系 → 1.0（被抗性抵消，无加成）
            电系精灵用电系技能打水系 → 2 * 1.5 = 3.0
        """
        value = TypeChart.multiplier(skill_type, defender)
        skill_ids = set(TypeChart.parse_types(skill_type))
        if skill_ids & set(TypeChart.parse_types(attacker)):
            value *= TypeChart.STAB
        return value

    # ──────────────────────────────────────────
    #  分类与查询
    # ──────────────────────────────────────────

    @staticmethod
    def classify(multiplier: float) -> str:
        """把倍率翻译成中文标签"""
        if multiplier == 0.0:
            return "无效"
        if multiplier > 1.0:
            return "克制"
        if multiplier < 1.0:
            return "微弱"
        return "普通"

    @staticmethod
    def _scan(defense: TypeLike) -> List[Tuple[str, float]]:
        """所有单属性打「defense」的倍率，按倍率从高到低排序"""
        rows = [
            (cn, TypeChart.multiplier(tid, defense))
            for tid, (cn, _) in ELEMENT_TYPES.items()
        ]
        rows.sort(key=lambda item: (-item[1], item[0]))
        return rows

    @staticmethod
    def weaknesses(defense: TypeLike) -> List[Tuple[str, float]]:
        """防守方的弱点（倍率 > 1）"""
        return [(n, m) for n, m in TypeChart._scan(defense) if m > 1.0]

    @staticmethod
    def resistances(defense: TypeLike) -> List[Tuple[str, float]]:
        """防守方的抗性（0 < 倍率 < 1）"""
        return [(n, m) for n, m in TypeChart._scan(defense) if 0.0 < m < 1.0]

    @staticmethod
    def immunities(defense: TypeLike) -> List[Tuple[str, float]]:
        """防守方的免疫（倍率 == 0）"""
        return [(n, m) for n, m in TypeChart._scan(defense) if m == 0.0]

    @staticmethod
    def defense_profile(defense: TypeLike) -> Dict[str, List[Tuple[str, float]]]:
        """防守方的完整属性资料: 弱点 / 抗性 / 免疫"""
        scan = TypeChart._scan(defense)
        return {
            "weaknesses": [(n, m) for n, m in scan if m > 1.0],
            "resistances": [(n, m) for n, m in scan if 0.0 < m < 1.0],
            "immunities": [(n, m) for n, m in scan if m == 0.0],
        }

    @staticmethod
    def offense_profile(attack: TypeLike) -> Dict[str, List[Tuple[str, float]]]:
        """攻击方的打击面: 克制 / 微弱 / 无效的单属性"""
        scan = [
            (cn, TypeChart.multiplier(attack, tid))
            for tid, (cn, _) in ELEMENT_TYPES.items()
        ]
        scan.sort(key=lambda item: (-item[1], item[0]))
        return {
            "strong": [(n, m) for n, m in scan if m > 1.0],
            "weak": [(n, m) for n, m in scan if 0.0 < m < 1.0],
            "immune": [(n, m) for n, m in scan if m == 0.0],
        }

    # ──────────────────────────────────────────
    #  展示
    # ──────────────────────────────────────────

    @staticmethod
    def format_profile(defense: TypeLike) -> str:
        """把防守方的属性资料格式化成一段可打印的文本"""
        profile = TypeChart.defense_profile(defense)
        label = TypeChart.label(defense)

        def render(rows: List[Tuple[str, float]]) -> str:
            return "  ".join(f"{name}{mult:g}x" for name, mult in rows) or "无"

        return (
            f"【{label}】\n"
            f"  弱点: {render(profile['weaknesses'])}\n"
            f"  抗性: {render(profile['resistances'])}\n"
            f"  免疫: {render(profile['immunities'])}"
        )


# ──────────────────────────────────────────
#  独立运行：快速测试
# ──────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"单属性数量: {len(TypeChart.all_types())}\n")

    print("-- 权威示例 --")
    print(f"  圣灵·地面 打 电·火 = {TypeChart.multiplier('圣灵·地面', '电·火')}   (期望 4)")
    print(f"  圣灵·超能 打 电·火 = {TypeChart.multiplier('圣灵·超能', '电·火')}   (期望 1.5)")
    print(f"  次元·电   打 地面  = {TypeChart.multiplier('次元·电', '地面')}    (期望 0.25)")
    print(f"  电        打 地面  = {TypeChart.multiplier('电', '地面')}        (期望 0)")

    print()
    for combo in ("电·火", "草·超能", "圣灵"):
        print(TypeChart.format_profile(combo))
        print()
