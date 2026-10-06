"""
命令行输出的格式化。
====================

这几个函数原本是 `Pokedex` 上的方法（print_monster / print_table /
print_effectiveness）。把展示逻辑粘在领域对象上有两个坏处：

  * 换一种界面（桌面客户端、Web）时，Pokedex 拖着一堆 print 走
  * 想验证「表格排得对不对」就得先建一个数据库连接

现在职责分开了：`Pokedex` 只负责查数据、返回 dict，怎么排版是这里的事。

**都返回字符串、不直接 print** —— 这样测试直接断言文本，不用去截 stdout。
要显示时调用方自己 `print()`。
"""

from typing import Dict, List, Optional

from database.attributes import SixAttributes


def monster(data: Dict) -> str:
    """单个精灵的信息块"""
    return '\n'.join([
        '=' * 50,
        f"  #{data.get('ID', '?')}  {data.get('DefName', '未知')}",
        '=' * 50,
        f"  属性: {data.get('TypeName') or data.get('Type', '?')}",
        f"  体力:{data.get('HP', '?')}  攻击:{data.get('Atk', '?')}"
        f"  防御:{data.get('Def', '?')}",
        f"  特攻:{data.get('SpAtk', '?')}  特防:{data.get('SpDef', '?')}"
        f"  速度:{data.get('Spd', '?')}",
        f"  种族值总和: {SixAttributes.from_row(data).total}",
    ])


def table(rows: List[Dict], title: str = '查询结果') -> str:
    """表格形式的查询结果"""
    if not rows:
        return f"\n[{title}] 无结果"

    lines = [
        f"\n{'─' * 68}",
        f"  {title} (共 {len(rows)} 条)",
        '─' * 68,
        f"{'ID':>5}  {'名称':<10} {'属性':<10} {'体力':>4} {'攻击':>4} "
        f"{'防御':>4} {'特攻':>4} {'特防':>4} {'速度':>4} {'总和':>5}",
        '-' * 68,
    ]
    for row in rows:
        type_text = row.get('TypeName') or row.get('Type', '')
        lines.append(
            f"{row.get('ID', ''):>5}  {row.get('DefName', ''):<10} {type_text:<10} "
            f"{row.get('HP', ''):>4} {row.get('Atk', ''):>4} {row.get('Def', ''):>4} "
            f"{row.get('SpAtk', ''):>4} {row.get('SpDef', ''):>4} {row.get('Spd', ''):>4} "
            f"{row.get('Total', ''):>5}"
        )
    return '\n'.join(lines)


def effectiveness(data: Optional[Dict]) -> str:
    """精灵的属性克制资料。

    data 来自 `Pokedex.get_type_effectiveness()`；传 None 表示这只精灵
    没有可识别的属性。
    """
    if not data:
        return '  ⚠️ 该精灵没有可识别的属性'

    def render(rows) -> str:
        if not rows:
            return '无'
        return '  '.join(f'{name} {mult:g}x' for name, mult in rows)

    return '\n'.join([
        f"{'─' * 50}",
        f"  {data['name']} 的属性克制 ({data['label']}系)",
        f"{'─' * 50}",
        f"  🔺 弱点: {render(data['weaknesses'])}",
        f"  🔹 抗性: {render(data['resistances'])}",
        f"  🚫 免疫: {render(data['immunities'])}",
    ])


def move_list(moves: List[Dict], title: str = '技能列表') -> str:
    """技能列表（含学习等级与效果文本）"""
    if not moves:
        return ''

    lines = [f"\n  {title} (共 {len(moves)} 个):"]
    for move in moves:
        level = move.get('LearningLv')
        level_text = f"Lv{level:<3}" if level is not None else '额外  '
        category = move.get('CategoryName') or move.get('Category', '')
        type_name = move.get('TypeName') or move.get('Type', '')
        lines.append(
            f"    {level_text} {move['Name']:<12} {type_name:<4} "
            f"{category:<3} 威力:{move.get('Power', '?'):<4} "
            f"PP:{move.get('MaxPP', '?')}"
        )
        if move.get('EffectText'):
            lines.append(f"         └ {move['EffectText']}")
    return '\n'.join(lines)
