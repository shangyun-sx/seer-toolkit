"""
精灵图鉴查询器 —— 基于 SQLite 的赛尔号精灵数据库。

支持:
- 按名字模糊搜索
- 按属性筛选 (含双属性)
- 按任意能力值排序
- 查看精灵的技能列表 (跨库关联)
- 属性克制: 列出精灵的弱点 / 抗性 / 免疫
"""

import json
import sqlite3
import threading
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

try:
    from database.attributes import FIELDS, TOTAL_SQL, SixAttributes
    from database.connections import ThreadLocalConnections
    from database.type_chart import ELEMENT_TYPES, TypeChart
except ImportError:  # 直接运行 database/pokedex.py 时
    from attributes import FIELDS, TOTAL_SQL, SixAttributes
    from connections import ThreadLocalConnections
    from type_chart import ELEMENT_TYPES, TypeChart

if TYPE_CHECKING:
    from database.effects import EffectParser


# 允许排序的列名白名单 —— 防止 SQL 注入
_ALLOWED_STATS = {'ID', 'DefName', 'Type', 'HP', 'Atk', 'Def',
                  'SpAtk', 'SpDef', 'Spd', 'Gender', 'IsDark', 'Total'}

# 列名中文映射
_STAT_CN = {
    'ID': '编号', 'DefName': '名称', 'Type': '属性',
    'HP': '体力', 'Atk': '攻击', 'Def': '防御',
    'SpAtk': '特攻', 'SpDef': '特防', 'Spd': '速度',
    'Total': '种族值总和',
}

# 不是真实列、需要换成表达式的排序字段。
# 表达式由 attributes.FIELDS 拼成，不掺任何用户输入
_SORT_EXPRESSIONS = {'Total': TOTAL_SQL}

# 属性名称 → 单属性 ID 映射（数据统一来自 database/type_chart.py）
_TYPE_NAME_TO_ID = {cn: tid for tid, (cn, _en) in ELEMENT_TYPES.items()}

# 反向映射：ID → 名称
_TYPE_ID_TO_NAME = {tid: cn for tid, (cn, _en) in ELEMENT_TYPES.items()}

# 数据库里可能存放属性的列名
_TYPE_COLUMNS = ('Type', 'Type2', 'SubType', 'SecondType', 'TypeB')

# 技能类别 (Moves.db 的 Category 列)
_MOVE_CATEGORY_CN = {1: '物理', 2: '特殊', 4: '属性'}


class Pokedex:
    """赛尔号精灵图鉴"""

    def __init__(self, data_dir: str):
        """
        data_dir: 包含 Monster.db, Moves.db 等文件的目录
        """
        self.data_dir = data_dir
        # 连接按线程各持一条 —— 共享一条连接在并发下会读到彼此的中间状态
        self._conns = ThreadLocalConnections(data_dir)
        self._effects: Optional[EffectParser] = None
        self._effects_lock = threading.Lock()

    # ──────────────────────────────────────────
    #  数据库连接管理
    # ──────────────────────────────────────────

    @property
    def monster_db(self) -> sqlite3.Connection:
        return self._conns.get('Monster.db')

    @property
    def move_db(self) -> sqlite3.Connection:
        return self._conns.get('Moves.db')

    @property
    def effects(self) -> 'EffectParser':
        """技能效果解析器（惰性创建，随 close() 一起释放）"""
        if self._effects is None:
            with self._effects_lock:
                if self._effects is None:   # 可能被别的线程先建好了
                    # 函数内 import：effects 模块不依赖 pokedex，但放这里可以
                    # 避免将来有人加反向依赖时出现循环导入
                    from database.effects import EffectParser
                    self._effects = EffectParser(self.data_dir)
        return self._effects

    def open_connections(self) -> int:
        """当前还开着的 sqlite 连接数（诊断 / 测试用）"""
        return self._conns.open_count()

    def close(self):
        """关闭所有数据库连接（含各线程各自持有的那些）"""
        self._conns.close()
        if self._effects:
            self._effects.close()
            self._effects = None

    # ──────────────────────────────────────────
    #  查询方法
    # ──────────────────────────────────────────

    def search(self, name: str) -> List[Dict]:
        """按名字模糊搜索精灵（排除皮肤 ID ≥ 15000）"""
        cur = self.monster_db.execute(
            "SELECT ID, DefName, Type, HP, Atk, Def, SpAtk, SpDef, Spd "
            "FROM monsters WHERE DefName LIKE ? AND ID < 15000 "
            "ORDER BY ID LIMIT 20",
            (f'%{name}%',)
        )
        return self._rows(cur.fetchall())

    def get_by_id(self, monster_id: int) -> Optional[Dict]:
        """按 ID 精确查询"""
        cur = self.monster_db.execute(
            "SELECT * FROM monsters WHERE ID = ?", (monster_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return self._add_type_name(dict(row))

    def filter_by_type(self, element: str, limit: int = 50) -> List[Dict]:
        """
        按属性筛选 (如 '火', '水', '草·超能')，双属性精灵也能被自己的
        任一属性筛出来。支持中文属性名、英文名或数字 ID。
        """
        # 数据库存的是「属性组合 ID」，所以要把所有含该属性的组合都算上
        combo_ids = TypeChart.combination_ids(element)
        if not combo_ids:
            return []

        placeholders = ','.join(['?'] * len(combo_ids))
        cur = self.monster_db.execute(
            f"SELECT ID, DefName, Type, HP, Atk, Def, SpAtk, SpDef, Spd "
            f"FROM monsters WHERE CAST(Type AS TEXT) IN ({placeholders}) "
            f"AND ID < 15000 ORDER BY ID LIMIT ?",
            [str(cid) for cid in combo_ids] + [limit]
        )
        return self._rows(cur.fetchall())

    def top_n(self, stat: str, n: int = 10) -> List[Dict]:
        """
        按某项能力值排名前 N 的精灵。
        stat 必须是 _ALLOWED_STATS 中的列名或 'Total' (白名单校验)。
        """
        if stat not in _ALLOWED_STATS:
            raise ValueError(
                f"不允许的排序字段: '{stat}'。"
                f"可选: {', '.join(_ALLOWED_STATS)}"
            )

        # 六维总是取全，这样每条结果都能算出种族值总和
        selected = ['ID', 'DefName', 'Type'] + list(FIELDS)
        if stat not in selected:
            # 'Total' 不是真实列，换成求和表达式；其它字段就是列名本身。
            # expression 来自白名单 / 模块常量，不掺用户输入
            expression = _SORT_EXPRESSIONS.get(stat, stat)
            selected.append(f'{expression} AS "{stat}"')

        # 使用参数化查询防止注入
        cur = self.monster_db.execute(
            f"SELECT {', '.join(selected)} "
            f'FROM monsters WHERE ID < 15000 ORDER BY "{stat}" DESC LIMIT ?',
            (n,)
        )
        return self._rows(cur.fetchall())

    def get_attributes(self, monster_id: int) -> Optional[SixAttributes]:
        """精灵的六维属性值对象（含种族值总和）"""
        monster = self.get_by_id(monster_id)
        if not monster:
            return None
        return SixAttributes.from_row(monster)

    def count(self) -> int:
        """获取精灵总数（排除皮肤）"""
        cur = self.monster_db.execute(
            "SELECT COUNT(*) as cnt FROM monsters WHERE ID < 15000"
        )
        return cur.fetchone()['cnt']

    # ──────────────────────────────────────────
    #  属性克制
    # ──────────────────────────────────────────

    @staticmethod
    def types_of(row) -> Tuple[int, ...]:
        """从一行记录里解析出属性 ID（单属性 1 个 / 双属性 2 个）。

        数据库把属性存成「属性组合 ID」:
            1 ~ 20 / 221 ~ 226  单属性
            21 ~ 132            双属性
        另外也兼容逗号分隔的多个 ID、以及额外的第二属性列。
        解析不出来的值会被跳过，不会影响其它查询。
        """
        try:
            keys = set(row.keys())
        except AttributeError:
            return ()

        ids: List[int] = []
        for column in _TYPE_COLUMNS:
            if column not in keys:
                continue
            value = row[column]
            if value in (None, '', 0):
                continue
            try:
                ids.extend(TypeChart.parse_types(value))
            except (ValueError, TypeError):
                continue

        return tuple(dict.fromkeys(ids))[:2]

    def get_monster_types(self, monster_id: int) -> Tuple[int, ...]:
        """精灵的属性 ID 元组"""
        monster = self.get_by_id(monster_id)
        return self.types_of(monster) if monster else ()

    def get_type_effectiveness(self, monster_id: int) -> Optional[Dict]:
        """精灵的属性克制资料: 弱点 / 抗性 / 免疫"""
        type_ids = self.get_monster_types(monster_id)
        if not type_ids:
            return None

        monster = self.get_by_id(monster_id) or {}
        return {
            'id': monster_id,
            'name': monster.get('DefName', ''),
            'types': list(type_ids),
            'label': TypeChart.label(type_ids),
            **TypeChart.defense_profile(type_ids),
        }

    # ──────────────────────────────────────────
    #  内部辅助
    # ──────────────────────────────────────────

    @staticmethod
    def _add_type_name(data: Dict) -> Dict:
        """给查询结果补可读字段：TypeName（属性名）和 Total（种族值总和）。

        Total 只在六列齐全时才算 —— top_n 可能只取了一部分列，
        缺列时算出来的和是错的，宁可不给。
        """
        raw = data.get('Type')
        try:
            data['TypeName'] = TypeChart.label(raw) if raw not in (None, '') else ''
        except (ValueError, TypeError):
            # 认不出来的属性值就原样显示，不要吞掉整条记录
            data['TypeName'] = str(raw)

        if all(column in data for column in FIELDS):
            data['Total'] = SixAttributes.from_row(data).total
        return data

    def _rows(self, rows) -> List[Dict]:
        return [self._add_type_name(dict(row)) for row in rows]

    @staticmethod
    def parse_move_entries(raw) -> List[Dict]:
        """解析 monsters.Moves 列。

        现在游戏里的数据是 JSON 数组，带学习等级：
            [{"ID":10006,"LearningLv":1,"Rec":0,"Tag":0}, ...]
        老版本可能是逗号分隔的技能 ID：
            "10006,20006,..."

        对应 SeerAPI 的 SkillInPet（skill + learning_level）。
        """
        if raw is None:
            return []
        text = str(raw).strip()
        if not text:
            return []

        # JSON 数组
        if text.startswith('['):
            try:
                data = json.loads(text)
            except ValueError:
                return []
            entries = []
            for item in data:
                if isinstance(item, dict) and item.get('ID') is not None:
                    entries.append(item)
                elif isinstance(item, int):
                    entries.append({'ID': item})
            return entries

        # 逗号分隔
        try:
            return [{'ID': int(x.strip())} for x in text.split(',') if x.strip()]
        except ValueError:
            return []

    def get_moves(self, monster_id: int, with_effects: bool = False) -> List[Dict]:
        """获取某精灵的技能列表 (跨库查询)，按学习等级排序。

        with_effects=True 时额外挂两个字段：
            Effects     效果描述列表（一个技能可能有多条效果）
            EffectText  用「；」连成一行，方便直接显示
        """
        monster = self.get_by_id(monster_id)
        if not monster:
            return []

        entries = self.parse_move_entries(monster.get('Moves'))
        if not entries:
            return []

        # 技能 ID → 学习等级
        learn_level = {}
        for entry in entries:
            learn_level.setdefault(entry['ID'], entry.get('LearningLv'))
        move_ids = list(learn_level)

        placeholders = ','.join(['?'] * len(move_ids))
        cur = self.move_db.execute(
            f"SELECT ID, Name, Type, Category, Power, MaxPP, Accuracy, "
            f"SideEffect, SideEffectArg "
            f"FROM moves WHERE ID IN ({placeholders})",
            move_ids
        )

        moves = []
        for row in cur.fetchall():
            data = self._add_type_name(dict(row))
            data['LearningLv'] = learn_level.get(data['ID'])
            data['CategoryName'] = _MOVE_CATEGORY_CN.get(
                data.get('Category'), str(data.get('Category') or '')
            )

            side_effect = data.pop('SideEffect', None)
            side_effect_arg = data.pop('SideEffectArg', None)
            if with_effects:
                texts = self.effects.render_move(side_effect, side_effect_arg)
                data['Effects'] = texts
                data['EffectText'] = '；'.join(texts)

            moves.append(data)

        # 有学习等级的按等级排前面，没有的（特训/额外技能）排后面
        moves.sort(key=lambda m: (
            m['LearningLv'] is None,
            m['LearningLv'] if m['LearningLv'] is not None else 0,
            m['ID'],
        ))
        return moves

    # ──────────────────────────────────────────
    #  格式化输出
    # ──────────────────────────────────────────

    def print_monster(self, monster: Dict) -> None:
        """美化打印单个精灵信息"""
        print(f"\n{'='*50}")
        print(f"  #{monster.get('ID', '?')}  {monster.get('DefName', '未知')}")
        print(f"{'='*50}")
        print(f"  属性: {monster.get('TypeName') or monster.get('Type', '?')}")
        print(f"  体力:{monster.get('HP','?')}  攻击:{monster.get('Atk','?')}"
              f"  防御:{monster.get('Def','?')}")
        print(f"  特攻:{monster.get('SpAtk','?')}  特防:{monster.get('SpDef','?')}"
              f"  速度:{monster.get('Spd','?')}")
        print(f"  种族值总和: {SixAttributes.from_row(monster).total}")

    def print_effectiveness(self, monster_id: int) -> None:
        """打印精灵的属性克制资料"""
        data = self.get_type_effectiveness(monster_id)
        if not data:
            print("  ⚠️ 该精灵没有可识别的属性")
            return

        print(f"\n{'─'*50}")
        print(f"  {data['name']} 的属性克制 ({data['label']}系)")
        print(f"{'─'*50}")

        def render(rows) -> str:
            if not rows:
                return "无"
            return "  ".join(f"{name} {mult:g}x" for name, mult in rows)

        print(f"  🔺 弱点: {render(data['weaknesses'])}")
        print(f"  🔹 抗性: {render(data['resistances'])}")
        print(f"  🚫 免疫: {render(data['immunities'])}")

    def print_table(self, rows: List[Dict], title: str = "查询结果") -> None:
        """表格形式打印查询结果"""
        if not rows:
            print(f"\n[{title}] 无结果")
            return

        print(f"\n{'─'*68}")
        print(f"  {title} (共 {len(rows)} 条)")
        print(f"{'─'*68}")
        header = (f"{'ID':>5}  {'名称':<10} {'属性':<10} {'体力':>4} {'攻击':>4} "
                  f"{'防御':>4} {'特攻':>4} {'特防':>4} {'速度':>4} {'总和':>5}")
        print(header)
        print('-' * 68)
        for r in rows:
            type_text = r.get('TypeName') or r.get('Type', '')
            print(f"{r.get('ID',''):>5}  {r.get('DefName',''):<10} {type_text:<10} "
                  f"{r.get('HP',''):>4} {r.get('Atk',''):>4} {r.get('Def',''):>4} "
                  f"{r.get('SpAtk',''):>4} {r.get('SpDef',''):>4} {r.get('Spd',''):>4} "
                  f"{r.get('Total',''):>5}")


# ──────────────────────────────────────────
#  独立运行：快速测试
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else 'data'
    dex = Pokedex(data_dir)

    print(f"精灵总数: {dex.count()}")

    # 搜索示例
    results = dex.search('雷伊')
    dex.print_table(results, "搜索 '雷伊'")

    # 排名前5体力
    top = dex.top_n('HP', 5)
    dex.print_table(top, "体力 Top 5")
