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
import sys
import os
from typing import Optional

# Windows GBK 终端下强制 UTF-8 输出。
# hasattr 不只是给 mypy 看的：stdout 被换成别的对象时（重定向、被测试框架
# 接管）很多实现没有 reconfigure，硬调会 AttributeError。
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import render
from config.ini_parser import IniParser
from config.account_manager import AccountManager
from config.paths import game_dir_of, remember_data_dir, resolve_data_dir
from database.pokedex import Pokedex
from database.integrity import IntegrityChecker
from database.type_chart import TypeChart


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

        def fmt_rows(rows) -> str:
            return "  ".join(f"{name} {mult:g}x" for name, mult in rows) or "无"

        print(f"\n{'═'*50}")
        print(f"  【{label}】属性克制")
        print(f"{'═'*50}")
        print(f"  ── 用 {label} 系技能攻击 ──")
        print(f"    🔺 克制: {fmt_rows(offense['strong'])}")
        print(f"    🔹 微弱: {fmt_rows(offense['weak'])}")
        print(f"    🚫 无效: {fmt_rows(offense['immune'])}")
        print(f"\n  ── {label} 系精灵受到攻击 ──")
        print(f"    🔺 弱点: {fmt_rows(defense['weaknesses'])}")
        print(f"    🔹 抗性: {fmt_rows(defense['resistances'])}")
        print(f"    🚫 免疫: {fmt_rows(defense['immunities'])}")

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


def main():
    parser = argparse.ArgumentParser(description='雷小伊配置管理器')
    # 这里以前是手写的参数循环，末尾单独一个 --data-dir 会被静默忽略；
    # 换成 argparse 顺手把这个坑填了。
    parser.add_argument('--data-dir', default=None,
                        help='数据目录（含 Monster.db）。默认取 $SEER_DATA_DIR，'
                             '再退到上次记住的目录，最后是 ./data')
    parser.add_argument('--game-dir', default=None,
                        help='雷小伊根目录（含 account.ini / Config/）。'
                             '默认取数据目录的上一级')
    parser.add_argument('--show-passwords', action='store_true',
                        help='明文显示账号密码（默认打码）')
    parser.add_argument('--debug', action='store_true',
                        help='出错时抛出完整堆栈，而不是只打印一行')
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    if args.data_dir:
        # 用户明确指定过就记下来，下次不用再输
        remember_data_dir(args.data_dir)
    game_dir = args.game_dir or game_dir_of(data_dir)

    app = App(game_dir, data_dir, show_passwords=args.show_passwords)
    debug = args.debug

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
        print(f"  雷小伊配置管理器 v1.0")
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
        elif choice in menu and menu[choice][1] is not None:
            try:
                menu[choice][1]()
            except FileNotFoundError as e:
                print(f"\n  ❌ 文件错误: {e}")
            except Exception as e:
                # 把异常吞成一行中文，等于把「到底哪一行炸的」彻底丢掉 ——
                # 交互式菜单里出问题时最难查的就是这个。默认至少给出异常
                # 类型和获取堆栈的办法；--debug 时干脆抛出去。
                if debug:
                    raise
                print(f"\n  ❌ 出错了: {type(e).__name__}: {e}")
                print("     （加 --debug 重新运行可以看到完整堆栈）")
        else:
            print("\n  ⚠️ 无效选项，请重新选择")


if __name__ == '__main__':
    main()
