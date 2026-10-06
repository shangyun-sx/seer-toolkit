"""
雷小伊配置管理器 —— 命令行版
==============================

一个学习项目，整合了 INI 解析、SQLite 操作、MD5 校验三大模块。

用法:
    python main.py                     # 交互式菜单
    python main.py --data-dir <路径>   # 指定数据目录（含 Monster.db）
    python main.py --game-dir <路径>   # 指定雷小伊根目录（含 account.ini）

目录解析统一走 config/paths.py，「数据目录」一律指含 Monster.db 的那个目录。
"""

import argparse
import logging
import sys
import os
from typing import Optional

# Windows GBK 终端下强制 UTF-8 输出。
# hasattr 不只是给 mypy 看的：stdout 被换成别的对象时（重定向、被测试框架
# 接管）很多实现没有 reconfigure，硬调会 AttributeError。
#
# stderr 也要一起改：只改 stdout 的话，`2>&1` 会把 UTF-8 的输出和 GBK 的
# 错误信息混进同一个管道，读的那端两种编码都按一种解，必然有一个是乱码。
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.platform == 'win32' and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import commands, render
from config.ini_parser import IniParser
from config.account_manager import AccountManager
from config.logsetup import setup_logging
from config.paths import game_dir_of, remember_data_dir, resolve_data_dir
from config.version import __version__
from database.pokedex import Pokedex
from database.integrity import IntegrityChecker
from database.type_chart import TypeChart

#: 诊断信息走 logging（打 stderr）；菜单和表格才是 print（打 stdout）
log = logging.getLogger(__name__)


class App:
    """主程序"""

    def __init__(self, game_dir: str, data_dir: str,
                 show_passwords: bool = False):
        """game_dir: 雷小伊根目录 —— account.ini / Config/ 在这儿
           data_dir: 数据目录   —— Monster.db 在这儿

        这两个以前是同一个参数（拿根目录再拼 '/data'），和 web 版/客户端
        对「数据目录」的理解正好相反。现在统一：凡是叫 data-dir 的都指
        含 Monster.db 的那个目录。

        show_passwords: 是否明文显示账号密码。默认关 —— 终端内容容易被
        截屏、录屏、贴进聊天框。
        """
        self.game_dir = game_dir
        self.data_dir = data_dir
        self.show_passwords = show_passwords
        self.mgr = AccountManager(game_dir)
        self.pokedex = Pokedex(data_dir)
        self.checker = IntegrityChecker(data_dir)

    # ──────────────────────────────────────────
    #  内部辅助
    # ──────────────────────────────────────────

    def _pick_account(self) -> Optional[str]:
        """让用户挑一个账号，返回 QQ 号；取消或没有账号时返回 None。

        以前这两个地方写死 accounts[0] —— 多账号时永远只操作第一个，
        而且界面上完全看不出来，用户以为在改第二个账号的任务。
        """
        accounts = self.mgr.list_accounts()
        if not accounts:
            print("\n  ⚠️ 未找到任何账号")
            return None
        if len(accounts) == 1:
            return accounts[0]['qq']

        print(f"\n  共 {len(accounts)} 个账号:")
        for index, acc in enumerate(accounts, 1):
            print(f"    [{index}] {acc['qq']}  ({acc['nick']})")

        raw = input("\n  选择账号编号 (直接回车取消): ").strip()
        if not raw:
            return None
        try:
            chosen = int(raw)
        except ValueError:
            print("  ⚠️ 请输入数字编号")
            return None
        if not 1 <= chosen <= len(accounts):
            print("  ⚠️ 编号超出范围")
            return None
        return accounts[chosen - 1]['qq']

    # ──────────────────────────────────────────
    #  菜单项
    # ──────────────────────────────────────────

    def show_accounts(self):
        """查看账号信息。

        密码默认打码 —— 终端内容很容易被截屏、录屏、或整个贴进聊天框。
        确实要看明文就加 --show-passwords。
        """
        accounts = self.mgr.list_accounts()
        if not accounts:
            print("\n  ⚠️ 未找到任何账号")
            return
        print(f"\n{'─'*50}")
        print(f"  账号列表 (共 {len(accounts)} 个)")
        print(f"{'─'*50}")
        for acc in accounts:
            print(f"  QQ: {acc['qq']}")
            print(f"  昵称: {acc['nick']}")
            if self.show_passwords:
                print(f"  密码: {acc['pass']}")
            else:
                print("  密码: ******  (要显示请加 --show-passwords)")
            print()

    def show_task_summary(self):
        """查看任务开关统计"""
        accounts = self.mgr.list_accounts()
        if not accounts:
            print("\n  ⚠️ 未找到任何账号")
            return

        for acc in accounts:
            qq = acc['qq']
            summary = self.mgr.task_summary(qq)
            print(f"\n{'─'*50}")
            print(f"  {qq} ({acc['nick']}) — 任务统计")
            print(f"{'─'*50}")
            print(f"  ✅ 已开启: {summary['enabled']} 个")
            print(f"  ❌ 已关闭: {summary['disabled']} 个")
            print(f"  📊 总计:   {summary['total']} 个")

    def search_pokedex(self):
        """精灵图鉴查询"""
        name = input("\n  请输入精灵名称 (支持模糊搜索): ").strip()
        if not name:
            print("  ⚠️ 名称不能为空")
            return

        results = self.pokedex.search(name)
        print(render.table(results, f"搜索 '{name}'"))

        if not results:
            return

        # 查看详情
        choice = input("\n  输入编号查看详情 (直接回车跳过): ").strip()
        if choice:
            try:
                mid = int(choice)
                monster = self.pokedex.get_by_id(mid)
                if monster:
                    print(render.monster(monster))
                    # 属性克制：查数据是 Pokedex 的事，排版是 render 的事
                    print(render.effectiveness(
                        self.pokedex.get_type_effectiveness(mid)))
                    # 技能
                    print(render.move_list(
                        self.pokedex.get_moves(mid, with_effects=True)))
                else:
                    print("  ⚠️ 未找到该编号的精灵")
            except ValueError:
                print("  ⚠️ 请输入有效编号")

    def type_effectiveness(self):
        """属性克制查询"""
        print(f"\n{'─'*50}")
        print("  属性克制查询")
        print(f"{'─'*50}")
        print("  · 输入属性名，如 火 / 电·火 / 圣灵·地面")
        print("  · 或输入精灵编号，查看该精灵的属性弱点")

        raw = input("\n  请输入 (直接回车返回): ").strip()
        if not raw:
            return

        # 纯数字当成精灵编号
        if raw.isdigit():
            print(render.effectiveness(
                self.pokedex.get_type_effectiveness(int(raw))))
            return

        try:
            label = TypeChart.label(raw)
        except ValueError as e:
            print(f"  ⚠️ {e}")
            return

        offense = TypeChart.offense_profile(raw)
        defense = TypeChart.defense_profile(raw)
        # 排版见 cli/render.py —— 子命令那边也要用同一份，别再内联一遍
        print(render.type_profile(label, offense, defense))

    def list_types(self):
        """列出全部属性"""
        types = TypeChart.all_types()
        print(f"\n{'─'*50}")
        print(f"  全部属性 (共 {len(types)} 个单属性)")
        print(f"{'─'*50}")

        row = []
        for _tid, cn, en in types:
            row.append(f"{cn}({en})")
            if len(row) == 4:
                print("    " + "".join(f"{x:<16}" for x in row))
                row = []
        if row:
            print("    " + "".join(f"{x:<16}" for x in row))

    def toggle_task(self):
        """切换任务开关"""
        qq = self._pick_account()
        if qq is None:
            return

        summary = self.mgr.task_summary(qq)

        print(f"\n  账号: {qq}")
        print(f"  已开启 {summary['enabled']} / {summary['total']} 个任务\n")

        task_id = input("  输入要切换的任务ID: ").strip()
        if not task_id:
            return

        new_state = self.mgr.toggle_task(qq, task_id)
        status_text = '✅ 开启' if new_state else '❌ 关闭'
        print(f"\n  任务_{task_id} → {status_text}")

    def check_integrity(self):
        """校验数据库文件"""
        self.checker.print_report()

    def show_config(self):
        """查看全局配置"""
        print(f"\n{'─'*40}")
        print(f"  全局配置")
        print(f"{'─'*40}")
        print(f"  游戏变速: {self.mgr.get_speed()}x")
        print(f"  静音:     {'是' if self.mgr.is_muted() else '否'}")
        print(f"  自动确认: {'是' if self.mgr.is_auto_confirm() else '否'}")


def run_menu(app: 'App', debug: bool) -> None:
    """交互式菜单 —— 不给子命令时的默认行为"""
    data_dir, game_dir = app.data_dir, app.game_dir

    menu = {
        '1': ('查看账号信息', app.show_accounts),
        '2': ('查看任务统计', app.show_task_summary),
        '3': ('精灵图鉴查询', app.search_pokedex),
        '4': ('切换任务开关', app.toggle_task),
        '5': ('校验数据库 MD5', app.check_integrity),
        '6': ('查看全局配置', app.show_config),
        '7': ('属性克制查询 (无需数据库)', app.type_effectiveness),
        '8': ('查看全部属性 (无需数据库)', app.list_types),
        '0': ('退出', None),
    }

    while True:
        print(f"\n{'='*50}")
        print(f"  雷小伊配置管理器 v{__version__}")
        print(f"  数据目录: {data_dir}")
        print(f"  游戏目录: {game_dir}")
        print(f"{'='*50}")
        for key, (label, _) in menu.items():
            print(f"  [{key}] {label}")
        print(f"{'='*50}")

        choice = input("\n  请选择: ").strip()
        if choice == '0':
            print("\n  再见! 👋")
            break

        entry = menu.get(choice)
        if entry is None or entry[1] is None:
            print("\n  ⚠️ 无效选项，请重新选择")
            continue

        handler = entry[1]
        try:
            handler()
        except FileNotFoundError as e:
            log.warning('文件错误: %s', e)
            print(f"\n  ❌ 文件错误: {e}")
        except Exception:
            # 堆栈交给 logging（打 stderr；--debug 时另存一份文件）。
            # 以前这里是 print(f"出错了: {e}")，把「哪一行炸的」彻底丢了 ——
            # 交互式菜单里出问题时最难查的就是这个。
            log.exception('菜单项执行失败')
            if debug:
                raise
            print("\n  ❌ 出错了 —— 上面是定位信息，加 --debug 可看完整堆栈")


def build_parser() -> argparse.ArgumentParser:
    """命令行参数。

    不给子命令时进交互式菜单；给了就非交互执行一次然后退出 ——
    这样这个工具能被脚本调用，也能 `--json | jq` 接进别的流程。
    """
    parser = argparse.ArgumentParser(
        description='雷小伊配置管理器（不给子命令时进交互式菜单）')
    # 这里以前是手写的参数循环，末尾单独一个 --data-dir 会被静默忽略
    parser.add_argument('--data-dir', default=None,
                        help='数据目录（含 Monster.db）。默认取 $SEER_DATA_DIR，'
                             '再退到上次记住的目录，最后是 ./data')
    parser.add_argument('--game-dir', default=None,
                        help='雷小伊根目录（含 account.ini / Config/）。'
                             '默认取数据目录的上一级')
    parser.add_argument('--show-passwords', action='store_true',
                        help='明文显示账号密码（默认打码）')
    parser.add_argument('--debug', action='store_true',
                        help='输出 DEBUG 日志并写日志文件；出错时抛完整堆栈')

    sub = parser.add_subparsers(dest='command', metavar='命令')

    def with_json(p, help_text='输出 JSON（给脚本 / jq 用）'):
        p.add_argument('--json', action='store_true', help=help_text)
        return p

    p = with_json(sub.add_parser('search', help='按名字搜索精灵'))
    p.add_argument('name', help='精灵名称关键词')
    p.add_argument('--limit', type=int, default=20, help='最多返回几条')

    p = with_json(sub.add_parser('by-type', help='按属性筛选精灵'))
    p.add_argument('element', help='属性名，如 火 / 电·火')
    p.add_argument('--limit', type=int, default=50, help='最多返回几条')

    p = with_json(sub.add_parser('top', help='按能力值排名'))
    p.add_argument('stat', help='排序字段，如 HP / Atk / Total')
    p.add_argument('-n', type=int, default=10, help='取前几名')

    with_json(sub.add_parser('types', help='列出全部单属性（不需要数据库）'))

    p = with_json(sub.add_parser('effectiveness', help='属性克制（属性名或精灵编号）'))
    p.add_argument('target', help='属性名（火 / 电·火）或精灵编号')

    with_json(sub.add_parser('integrity', help='校验数据库完整性'))
    with_json(sub.add_parser('accounts', help='列出账号（默认不含密码）'))

    return parser


def main() -> int:
    args = build_parser().parse_args()
    log_path = setup_logging(debug=args.debug)

    data_dir = resolve_data_dir(args.data_dir)
    if args.data_dir:
        # 用户明确指定过就记下来，下次不用再输
        remember_data_dir(args.data_dir)
    game_dir = args.game_dir or game_dir_of(data_dir)

    if args.command is None:
        app = App(game_dir, data_dir, show_passwords=args.show_passwords)
        if log_path:
            print(f"日志: {log_path}")
        run_menu(app, args.debug)
        return 0

    # ── 非交互模式 ──────────────────────
    if args.command == 'types':
        return commands.list_types(as_json=args.json)
    if args.command == 'integrity':
        return commands.integrity(data_dir, as_json=args.json)
    if args.command == 'accounts':
        return commands.accounts(game_dir, as_json=args.json,
                                 show_passwords=args.show_passwords)

    app = App(game_dir, data_dir, show_passwords=args.show_passwords)
    try:
        if args.command == 'search':
            return commands.search(app.pokedex, args.name, args.limit, args.json)
        if args.command == 'by-type':
            return commands.by_type(app.pokedex, args.element, args.limit, args.json)
        if args.command == 'top':
            return commands.top(app.pokedex, args.stat, args.n, args.json)
        if args.command == 'effectiveness':
            return commands.effectiveness(app.pokedex, args.target, args.json)
    except FileNotFoundError as e:
        return commands._fail(f'找不到数据库: {e}')
    finally:
        app.pokedex.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
