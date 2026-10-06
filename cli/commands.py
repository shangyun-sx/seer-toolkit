"""
非交互式子命令。
================

交互式菜单适合人坐着点，但没法脚本化 —— 想「查一下火系有多少只」得开个终端
一层层敲菜单，还没法把结果喂给别的程序。这里给每个查询配一个子命令：

    python main.py search 雷伊            # 人看的表格
    python main.py search 雷伊 --json     # 机器读的 JSON
    python main.py by-type 火 --limit 5

**只依赖 Pokedex / IntegrityChecker / cli.render，不碰 main.App** —— 否则
入口和命令模块会互相 import。

日志走 stderr、输出走 stdout，所以 `--json | jq` 不会被日志行污染。
"""

import json
import sys
from typing import Any, Dict, List

from cli import render
from config.account_manager import AccountManager
from database.integrity import IntegrityChecker
from database.pokedex import Pokedex
from database.type_chart import TypeChart


def emit(payload: Any, as_json: bool, text: str) -> None:
    """统一出口：--json 打 JSON，否则打人看的文本"""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


def _fail(message: str) -> int:
    """命令级的错误：写 stderr 并返回非零，别和正常输出混在一起"""
    print(message, file=sys.stderr)
    return 1


# ──────────────────────────────────────────
#  查询类
# ──────────────────────────────────────────

def search(dex: Pokedex, name: str, limit: int = 20, as_json: bool = False) -> int:
    """按名字模糊搜索"""
    rows: List[Dict] = dex.search(name, limit=limit)
    total = dex.count_search(name)
    emit(
        {'query': name, 'total': total, 'shown': len(rows), 'results': rows},
        as_json,
        render.table(rows, f"搜索 '{name}' ({total} 条)"),
    )
    return 0


def by_type(dex: Pokedex, element: str, limit: int = 50,
            as_json: bool = False) -> int:
    """按属性筛选"""
    try:
        rows = dex.filter_by_type(element, limit=limit)
        total = dex.count_by_type(element)
    except ValueError as e:
        return _fail(str(e))

    emit(
        {'element': element, 'total': total, 'shown': len(rows), 'results': rows},
        as_json,
        render.table(rows, f'{element}系精灵 ({total} 条)'),
    )
    return 0


def top(dex: Pokedex, stat: str, n: int = 10, as_json: bool = False) -> int:
    """按某项能力值排名"""
    try:
        rows = dex.top_n(stat, n)
    except ValueError as e:
        return _fail(str(e))

    emit(
        {'stat': stat, 'count': len(rows), 'results': rows},
        as_json,
        render.table(rows, f'{stat} Top {n}'),
    )
    return 0


def list_types(as_json: bool = False) -> int:
    """列出全部单属性（不需要数据库）"""
    types = [{'id': tid, 'name': cn, 'name_en': en}
             for tid, cn, en in TypeChart.all_types()]
    emit(
        {'count': len(types), 'types': types},
        as_json,
        '\n'.join(['', '  全部单属性:', '  ' + '  '.join(
            f'{t["name"]}({t["name_en"]})' for t in types)]),
    )
    return 0


def effectiveness(dex: Pokedex, target: str, as_json: bool = False) -> int:
    """属性克制。target 是属性名（火 / 电·火），或精灵编号"""
    if target.isdigit():
        data = dex.get_type_effectiveness(int(target))
        if data is None:
            return _fail(f'精灵 #{target} 不存在或没有可识别的属性')
        emit(data, as_json, render.effectiveness(data))
        return 0

    try:
        label = TypeChart.label(target)
    except ValueError as e:
        return _fail(str(e))

    offense = TypeChart.offense_profile(target)
    defense = TypeChart.defense_profile(target)
    emit(
        {'element': label, 'offense': offense, 'defense': defense},
        as_json,
        render.type_profile(label, offense, defense),
    )
    return 0


def integrity(data_dir: str, as_json: bool = False) -> int:
    """校验数据库完整性。有异常项就返回非零，方便脚本判断"""
    checker = IntegrityChecker(data_dir)
    ok, matched, mismatched = checker.verify()

    if as_json:
        emit({'ok': ok, 'matched': matched, 'mismatched': mismatched}, True, '')
    else:
        checker.print_report()
    return 0 if ok else 1


def accounts(game_dir: str, as_json: bool = False,
             show_passwords: bool = False) -> int:
    """列出账号。默认不含密码 —— 输出可能被重定向进文件"""
    if as_json:
        items = AccountManager(game_dir).list_accounts()
        for item in items:
            item.pop('pass', None)
        emit({'count': len(items), 'accounts': items}, True, '')
        return 0

    mgr = AccountManager(game_dir)
    items = mgr.list_accounts()
    if not items:
        print('  ⚠️ 未找到任何账号')
        return 0

    lines = ['', f'  账号列表 (共 {len(items)} 个)', '─' * 40]
    for acc in items:
        lines.append(f"  {acc['qq']}  {acc['nick']}")
        if show_passwords:
            lines.append(f"      密码: {acc['pass']}")
    print('\n'.join(lines))
    return 0
