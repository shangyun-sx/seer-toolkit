"""
账号与任务配置管理器。

管理:
- account.ini: 账号密码 (QQ号关联)
- Config/<QQ号>.ini: 每个账号的日常任务开关
- Config.ini: 登录器全局设置
"""

import os
from typing import Dict, List, Tuple
from .ini_parser import IniParser


class AccountManager:
    """统一管理账号和任务配置"""

    def __init__(self, base_dir: str):
        """
        base_dir: 雷小伊根目录 (包含 account.ini, Config.ini, Config/)
        """
        self.base_dir = base_dir

        # 加载核心配置文件
        self.account_ini = IniParser(os.path.join(base_dir, 'account.ini'))
        self.global_config = IniParser(os.path.join(base_dir, 'Config.ini'))

    # ──────────────────────────────────────────
    #  账号管理
    # ──────────────────────────────────────────

    def list_accounts(self) -> List[Dict[str, str]]:
        """列出所有已保存的账号"""
        accounts = []
        for qq in self.account_ini.sections():
            accounts.append({
                'qq': qq,
                'pass': self.account_ini.get(qq, 'pass', '***'),
                'nick': self.account_ini.get(qq, 'nick', '未知'),
            })
        return accounts

    def get_account(self, qq: str) -> Dict[str, str]:
        """获取单个账号信息"""
        return {
            'qq': qq,
            'pass': self.account_ini.get(qq, 'pass', '***'),
            'nick': self.account_ini.get(qq, 'nick', '未知'),
        }

    # ──────────────────────────────────────────
    #  任务配置 (Config/<QQ>.ini)
    # ──────────────────────────────────────────

    def get_task_config(self, qq: str) -> IniParser:
        """加载某个账号的任务配置文件"""
        config_path = os.path.join(self.base_dir, 'Config', f'{qq}.ini')
        if os.path.exists(config_path):
            return IniParser(config_path)
        return IniParser()

    def list_tasks(self, qq: str) -> List[Dict]:
        """列出某个账号的所有任务及其状态"""
        task_ini = self.get_task_config(qq)
        tasks = []
        for section in task_ini.sections():
            if section.startswith('任务_'):
                task_id = section.replace('任务_', '')
                # 部分任务有额外配置 (如子选项)
                extra = {k: v for k, v in task_ini.items(section) if k != '开关'}
                tasks.append({
                    'id': task_id,
                    'enabled': task_ini.get_bool(section, '开关', False),
                    'extra': extra,
                })
        return tasks

    def task_summary(self, qq: str) -> Dict:
        """任务统计摘要"""
        tasks = self.list_tasks(qq)
        enabled = [t for t in tasks if t['enabled']]
        disabled = [t for t in tasks if not t['enabled']]
        return {
            'total': len(tasks),
            'enabled': len(enabled),
            'disabled': len(disabled),
            'enabled_list': enabled,
            'disabled_list': disabled,
        }

    def toggle_task(self, qq: str, task_id: str, enable: bool = None) -> bool:
        """切换某个任务的开关状态"""
        task_ini = self.get_task_config(qq)
        section = f'任务_{task_id}'

        if enable is None:
            # 翻转：0→1, 1→0
            current = task_ini.get_bool(section, '开关', False)
            enable = not current

        task_ini.set(section, '开关', '1' if enable else '0')
        config_path = os.path.join(self.base_dir, 'Config', f'{qq}.ini')
        task_ini.save(config_path)
        return enable

    # ──────────────────────────────────────────
    #  全局设置
    # ──────────────────────────────────────────

    def get_speed(self) -> int:
        """获取游戏变速倍率"""
        return self.global_config.get_int('登录器', '变速', 1)

    def is_muted(self) -> bool:
        """是否静音"""
        return self.global_config.get_bool('登录器', '静音', False)

    def is_auto_confirm(self) -> bool:
        """是否自动确认"""
        return self.global_config.get_bool('登录器', '自动确定', False)


# ──────────────────────────────────────────
#  独立运行：快速测试
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else '.'
    mgr = AccountManager(base)

    print("===== 账号列表 =====")
    for acc in mgr.list_accounts():
        print(f"  QQ: {acc['qq']}, 昵称: {acc['nick']}")

    if mgr.list_accounts():
        qq = mgr.list_accounts()[0]['qq']
        summary = mgr.task_summary(qq)
        print(f"\n===== {qq} 任务统计 =====")
        print(f"  开启: {summary['enabled']} 个")
        print(f"  关闭: {summary['disabled']} 个")
        print(f"  总计: {summary['total']} 个")
