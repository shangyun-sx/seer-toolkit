"""
雷小伊配置管理器 —— 命令行版
==============================

一个学习项目，整合了 INI 解析、SQLite 操作、MD5 校验三大模块。

用法:
    python main.py                    # 交互式菜单
    python main.py --data-dir <路径>  # 指定数据目录
"""

import sys
import os

# Windows GBK 终端下强制 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.ini_parser import IniParser
from config.account_manager import AccountManager
from database.pokedex import Pokedex
from database.integrity import IntegrityChecker


class App:
    """主程序"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.mgr = AccountManager(data_dir)
        self.pokedex = Pokedex(os.path.join(data_dir, 'data'))
        self.checker = IntegrityChecker(os.path.join(data_dir, 'data'))

    # ──────────────────────────────────────────
    #  菜单项
    # ──────────────────────────────────────────

    def show_accounts(self):
        """查看账号信息"""
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
            print(f"  密码: {acc['pass']}")
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
        self.pokedex.print_table(results, f"搜索 '{name}'")

        if not results:
            return

        # 查看详情
        choice = input("\n  输入编号查看详情 (直接回车跳过): ").strip()
        if choice:
            try:
                mid = int(choice)
                monster = self.pokedex.get_by_id(mid)
                if monster:
                    self.pokedex.print_monster(monster)
                    # 查询技能
                    moves = self.pokedex.get_moves(mid)
                    if moves:
                        print(f"\n  技能列表:")
                        for m in moves:
                            print(f"    {m['Name']} ({m['Type']}) "
                                  f"威力:{m.get('Power','?')} "
                                  f"PP:{m.get('MaxPP','?')}")
                else:
                    print("  ⚠️ 未找到该编号的精灵")
            except ValueError:
                print("  ⚠️ 请输入有效编号")

    def toggle_task(self):
        """切换任务开关"""
        accounts = self.mgr.list_accounts()
        if not accounts:
            print("\n  ⚠️ 未找到任何账号")
            return

        qq = accounts[0]['qq']  # 默认第一个账号
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
    # 解析命令行参数
    data_dir = '.'
    for i, arg in enumerate(sys.argv):
        if arg == '--data-dir' and i + 1 < len(sys.argv):
            data_dir = sys.argv[i + 1]

    # 切换到脚本所在目录，方便相对路径引用
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 如果 data_dir 是相对路径，基于脚本目录解析
    if not os.path.isabs(data_dir):
        # 优先尝试当前目录
        if not os.path.exists(data_dir):
            # 尝试雷小伊目录
            alt = os.path.join(os.path.dirname(script_dir), data_dir)
            if os.path.exists(alt):
                data_dir = alt

    app = App(data_dir)

    menu = {
        '1': ('查看账号信息', app.show_accounts),
        '2': ('查看任务统计', app.show_task_summary),
        '3': ('精灵图鉴查询', app.search_pokedex),
        '4': ('切换任务开关', app.toggle_task),
        '5': ('校验数据库 MD5', app.check_integrity),
        '6': ('查看全局配置', app.show_config),
        '0': ('退出', None),
    }

    while True:
        print(f"\n{'='*50}")
        print(f"  雷小伊配置管理器 v1.0")
        print(f"  数据目录: {data_dir}")
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
                print(f"\n  ❌ 出错了: {e}")
        else:
            print("\n  ⚠️ 无效选项，请重新选择")


if __name__ == '__main__':
    main()
