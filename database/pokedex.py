"""
精灵图鉴查询器 —— 基于 SQLite 的赛尔号精灵数据库。

支持:
- 按名字模糊搜索
- 按属性筛选
- 按任意能力值排序
- 查看精灵的技能列表 (跨库关联)
"""

import sqlite3
import os
from typing import List, Dict, Optional


# 允许排序的列名白名单 —— 防止 SQL 注入
_ALLOWED_STATS = {'ID', 'DefName', 'Type', 'HP', 'Atk', 'Def',
                  'SpAtk', 'SpDef', 'Spd', 'Gender', 'IsDark'}

# 列名中文映射
_STAT_CN = {
    'ID': '编号', 'DefName': '名称', 'Type': '属性',
    'HP': '体力', 'Atk': '攻击', 'Def': '防御',
    'SpAtk': '特攻', 'SpDef': '特防', 'Spd': '速度',
}


class Pokedex:
    """赛尔号精灵图鉴"""

    def __init__(self, data_dir: str):
        """
        data_dir: 包含 Monster.db, Moves.db 等文件的目录
        """
        self.data_dir = data_dir
        self._monster_conn: Optional[sqlite3.Connection] = None
        self._move_conn: Optional[sqlite3.Connection] = None

    # ──────────────────────────────────────────
    #  数据库连接管理
    # ──────────────────────────────────────────

    @property
    def monster_db(self) -> sqlite3.Connection:
        if self._monster_conn is None:
            db_path = os.path.join(self.data_dir, 'Monster.db')
            if not os.path.exists(db_path):
                raise FileNotFoundError(f"数据库不存在: {db_path}")
            self._monster_conn = sqlite3.connect(db_path)
            self._monster_conn.row_factory = sqlite3.Row  # 支持字典式访问
        return self._monster_conn

    @property
    def move_db(self) -> sqlite3.Connection:
        if self._move_conn is None:
            db_path = os.path.join(self.data_dir, 'Moves.db')
            if not os.path.exists(db_path):
                raise FileNotFoundError(f"数据库不存在: {db_path}")
            self._move_conn = sqlite3.connect(db_path)
            self._move_conn.row_factory = sqlite3.Row
        return self._move_conn

    def close(self):
        """关闭所有数据库连接"""
        if self._monster_conn:
            self._monster_conn.close()
            self._monster_conn = None
        if self._move_conn:
            self._move_conn.close()
            self._move_conn = None

    # ──────────────────────────────────────────
    #  查询方法
    # ──────────────────────────────────────────

    def search(self, name: str) -> List[Dict]:
        """按名字模糊搜索精灵"""
        cur = self.monster_db.execute(
            "SELECT ID, DefName, Type, HP, Atk, Def, SpAtk, SpDef, Spd "
            "FROM monsters WHERE DefName LIKE ? "
            "ORDER BY ID LIMIT 20",
            (f'%{name}%',)
        )
        return [dict(row) for row in cur.fetchall()]

    def get_by_id(self, monster_id: int) -> Optional[Dict]:
        """按 ID 精确查询"""
        cur = self.monster_db.execute(
            "SELECT * FROM monsters WHERE ID = ?", (monster_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def filter_by_type(self, element: str) -> List[Dict]:
        """按属性筛选 (如 '火', '水', '草')"""
        cur = self.monster_db.execute(
            "SELECT ID, DefName, Type, HP, Atk, Def, SpAtk, SpDef, Spd "
            "FROM monsters WHERE Type LIKE ? "
            "ORDER BY ID LIMIT 50",
            (f'%{element}%',)
        )
        return [dict(row) for row in cur.fetchall()]

    def top_n(self, stat: str, n: int = 10) -> List[Dict]:
        """
        按某项能力值排名前 N 的精灵。
        stat 必须是 _ALLOWED_STATS 中的列名 (白名单校验)。
        """
        if stat not in _ALLOWED_STATS:
            raise ValueError(
                f"不允许的排序字段: '{stat}'。"
                f"可选: {', '.join(_ALLOWED_STATS)}"
            )
        # 使用参数化查询防止注入
        cur = self.monster_db.execute(
            f"SELECT ID, DefName, Type, {stat} "
            f"FROM monsters ORDER BY {stat} DESC LIMIT ?",
            (n,)
        )
        return [dict(row) for row in cur.fetchall()]

    def count(self) -> int:
        """获取精灵总数"""
        cur = self.monster_db.execute("SELECT COUNT(*) as cnt FROM monsters")
        return cur.fetchone()['cnt']

    def get_moves(self, monster_id: int) -> List[Dict]:
        """获取某精灵的技能列表 (跨库查询)"""
        monster = self.get_by_id(monster_id)
        if not monster:
            return []

        # Moves 字段可能存有技能 ID 列表 (逗号分隔)
        moves_str = monster.get('Moves', '')
        if not moves_str:
            return []

        # 解析技能 ID
        try:
            move_ids = [int(x.strip()) for x in moves_str.split(',') if x.strip()]
        except ValueError:
            return []

        if not move_ids:
            return []

        # 查询技能详情
        placeholders = ','.join(['?'] * len(move_ids))
        cur = self.move_db.execute(
            f"SELECT ID, Name, Type, Category, Power, MaxPP, Accuracy "
            f"FROM moves WHERE ID IN ({placeholders}) "
            f"ORDER BY ID LIMIT 20",
            move_ids
        )
        return [dict(row) for row in cur.fetchall()]

    # ──────────────────────────────────────────
    #  格式化输出
    # ──────────────────────────────────────────

    def print_monster(self, monster: Dict) -> None:
        """美化打印单个精灵信息"""
        print(f"\n{'='*50}")
        print(f"  #{monster.get('ID', '?')}  {monster.get('DefName', '未知')}")
        print(f"{'='*50}")
        print(f"  属性: {monster.get('Type', '?')}")
        print(f"  体力:{monster.get('HP','?')}  攻击:{monster.get('Atk','?')}"
              f"  防御:{monster.get('Def','?')}")
        print(f"  特攻:{monster.get('SpAtk','?')}  特防:{monster.get('SpDef','?')}"
              f"  速度:{monster.get('Spd','?')}")

    def print_table(self, rows: List[Dict], title: str = "查询结果") -> None:
        """表格形式打印查询结果"""
        if not rows:
            print(f"\n[{title}] 无结果")
            return

        print(f"\n{'─'*60}")
        print(f"  {title} (共 {len(rows)} 条)")
        print(f"{'─'*60}")
        header = f"{'ID':>5}  {'名称':<10} {'属性':<8} {'体力':>4} {'攻击':>4} {'防御':>4} {'特攻':>4} {'特防':>4} {'速度':>4}"
        print(header)
        print('-' * 60)
        for r in rows:
            print(f"{r.get('ID',''):>5}  {r.get('DefName',''):<10} {r.get('Type',''):<8} "
                  f"{r.get('HP',''):>4} {r.get('Atk',''):>4} {r.get('Def',''):>4} "
                  f"{r.get('SpAtk',''):>4} {r.get('SpDef',''):>4} {r.get('Spd',''):>4}")


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
