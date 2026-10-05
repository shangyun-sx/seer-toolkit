"""
六维属性值对象
==============

精灵的体力 / 攻击 / 防御 / 特攻 / 特防 / 速度，在数据库里是六个独立的列，
散落在各处传来传去。封成一个值对象之后，「种族值总和」这类派生数据就有了
自然的落点 —— 以前只能一项一项排。

思路学的是 SeerAPI 的 `SixAttributes`
（packages/seerapi-models/seerapi_models/common.py），但有两处**故意不一样**：

  * 那边用 pydantic，这里用标准库的 `dataclass` —— 本项目不引入额外依赖
  * 那边有 `from_string()` 和百分比运算。本项目的数据库把六维存成六个整数列，
    **没有**空格分隔的字符串形式（已确认），也不做学习力/个体值的复合计算，
    所以这两块没有搬过来 —— 搬了就是没人用的死代码

关于顺序：SeerAPI 内部按「体力在最后」组织，所以它的 `from_list` 有个
`hp_first` 开关。本项目直接采用**数据库的顺序**（体力在前），于是这个开关
就没有存在的必要了。`FIELDS` 同时是 SQL 排序表达式的唯一来源。
"""

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

#: 数据库列名，**顺序就是数据库里的顺序**（体力在前）
FIELDS = ('HP', 'Atk', 'Def', 'SpAtk', 'SpDef', 'Spd')

#: 列名 → 中文标签
LABELS = {
    'HP': '体力',
    'Atk': '攻击',
    'Def': '防御',
    'SpAtk': '特攻',
    'SpDef': '特防',
    'Spd': '速度',
}

#: 列名 → dataclass 字段名（`def` 是 Python 关键字，所以防御叫 def_）
_FIELD_NAMES = ('hp', 'atk', 'def_', 'sp_atk', 'sp_def', 'spd')

#: 「种族值总和」的 SQL 表达式，供 top_n 排序用。
#: 由 FIELDS 拼出来，不手写 —— 以后加一项属性只用改 FIELDS
TOTAL_SQL = ' + '.join(FIELDS)


@dataclass(frozen=True)
class SixAttributes:
    """精灵的六维属性。

        attrs = SixAttributes.from_row(monster)
        attrs.total      # 种族值总和
        attrs.hp, attrs.spd, ...
    """

    hp: int = 0
    atk: int = 0
    def_: int = 0
    sp_atk: int = 0
    sp_def: int = 0
    spd: int = 0

    @property
    def total(self) -> int:
        """种族值总和"""
        return self.hp + self.atk + self.def_ + self.sp_atk + self.sp_def + self.spd

    @classmethod
    def from_list(cls, values: Sequence[int]) -> 'SixAttributes':
        """按 `FIELDS` 的顺序构建（体力在前）"""
        if len(values) < len(_FIELD_NAMES):
            raise ValueError(
                f"需要 {len(_FIELD_NAMES)} 个属性值，实际给了 {len(values)} 个"
            )
        return cls(**{name: int(value)
                      for name, value in zip(_FIELD_NAMES, values)})

    @classmethod
    def from_row(cls, row: Mapping) -> 'SixAttributes':
        """从一行数据库记录构建（dict 或 sqlite3.Row）。

        缺失的列按 0 处理 —— 图鉴查询不一定把所有列都 SELECT 出来。
        """
        values = []
        for column in FIELDS:
            try:
                value = row[column]
            except (KeyError, IndexError, TypeError):
                value = 0
            values.append(int(value or 0))
        return cls.from_list(values)

    def as_dict(self) -> Dict[str, int]:
        """列名 → 数值，方便直接拼进 API 返回值"""
        return {column: getattr(self, name)
                for column, name in zip(FIELDS, _FIELD_NAMES)}

    def __str__(self) -> str:
        return '  '.join(f"{LABELS[column]}:{value}"
                         for column, value in self.as_dict().items())


# ──────────────────────────────────────────
#  独立运行：快速测试
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys

    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    leiyi = SixAttributes.from_list([71, 108, 70, 101, 77, 105])
    print(f"雷伊: {leiyi}")
    print(f"  种族值总和: {leiyi.total}")
    print(f"  SQL 表达式: {TOTAL_SQL}")
    print()
    print(f"从行构建: {SixAttributes.from_row({'HP': 55, 'Atk': 69, 'Def': 65})}")
