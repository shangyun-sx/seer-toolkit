"""
测试账号与任务配置管理（config/account_manager.py）。

这个模块此前覆盖率 0% —— 而它恰恰是**会写回游戏配置**的那一个：
`toggle_task()` 直接改 `Config/<QQ>.ini`。B1 修的就是「save() 把注释抹掉」，
所以这里补一个端到端回归测试，把那条链路钉住。

运行: python -m pytest tests/test_account_manager.py -v
  或: python tests/test_account_manager.py
"""

import os
import sys
import tempfile

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.account_manager import AccountManager

#: 故意带注释：B1 之前 save() 会把它们全抹掉
TASK_INI = ('; 雷小伊任务配置\n'
            '; 由登录器生成，请勿手改\n'
            '\n'
            '[任务_1]\n'
            '; 每日签到\n'
            '开关=0\n'
            '\n'
            '[任务_2]\n'
            '开关=1\n')


def _make_game_dir(tmp, accounts=(('12345', '小明'),)):
    """造一个最小的雷小伊根目录：account.ini + Config/<QQ>.ini"""
    os.makedirs(os.path.join(tmp, 'Config'), exist_ok=True)

    with open(os.path.join(tmp, 'account.ini'), 'w', encoding='gbk') as f:
        for qq, nick in accounts:
            f.write(f'[{qq}]\npass=SECRET_{qq}\nnick={nick}\n\n')

    for qq, _nick in accounts:
        with open(os.path.join(tmp, 'Config', f'{qq}.ini'),
                  'w', encoding='gbk') as f:
            f.write(TASK_INI)

    with open(os.path.join(tmp, 'Config.ini'), 'w', encoding='gbk') as f:
        f.write('[登录器]\n变速=3\n静音=1\n自动确定=1\n')
    return tmp


def _read(path):
    with open(path, encoding='gbk') as f:
        return f.read()


# ──────────────────────────────────────────
#  账号
# ──────────────────────────────────────────

def test_list_accounts():
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp, [('12345', '小明'), ('67890', '小红')])
        accounts = AccountManager(tmp).list_accounts()

        assert [a['qq'] for a in accounts] == ['12345', '67890']
        assert accounts[0]['nick'] == '小明'
        assert all('SECRET' in a['pass'] for a in accounts)


def test_list_accounts_when_no_file():
    """没有 account.ini 时给空列表，不是抛异常"""
    with tempfile.TemporaryDirectory() as tmp:
        assert AccountManager(tmp).list_accounts() == []


def test_get_account():
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        acc = AccountManager(tmp).get_account('12345')
        assert acc['nick'] == '小明'
        assert acc['pass'] == 'SECRET_12345'


# ──────────────────────────────────────────
#  任务
# ──────────────────────────────────────────

def test_list_tasks_only_picks_task_sections():
    """只有 任务_ 开头的节才算任务"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        with open(os.path.join(tmp, 'Config', '12345.ini'), 'a',
                  encoding='gbk') as f:
            f.write('\n[其他设置]\n开关=1\n')

        tasks = AccountManager(tmp).list_tasks('12345')
        assert [t['id'] for t in tasks] == ['1', '2']


def test_list_tasks_reads_switch():
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        tasks = {t['id']: t['enabled'] for t in AccountManager(tmp).list_tasks('12345')}
        assert tasks == {'1': False, '2': True}


def test_task_summary():
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        summary = AccountManager(tmp).task_summary('12345')
        assert summary['total'] == 2
        assert summary['enabled'] == 1
        assert summary['disabled'] == 1


def test_toggle_task_flips_the_switch():
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        mgr = AccountManager(tmp)

        assert mgr.toggle_task('12345', '1') is True     # 0 -> 1
        assert mgr.toggle_task('12345', '1') is False    # 1 -> 0

        assert mgr.toggle_task('12345', '1', enable=True) is True

        tasks = {t['id']: t['enabled'] for t in mgr.list_tasks('12345')}
        assert tasks['1'] is True


def test_toggle_task_preserves_comments():
    """端到端钉住 B1：改开关不能把游戏配置里的注释抹掉。

    旧版 save() 是从内存整份重新序列化，注释和空行全丢 —— 用户点一下
    开关，游戏配置就被改写了。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        config_path = os.path.join(tmp, 'Config', '12345.ini')

        AccountManager(tmp).toggle_task('12345', '1')

        after = _read(config_path)
        assert '; 雷小伊任务配置' in after, f'注释被抹掉了:\n{after}'
        assert '; 由登录器生成，请勿手改' in after
        assert '; 每日签到' in after
        assert '开关=1' in after
        assert '\n\n' in after, '空行丢了'
        # 另一个任务没被动过
        assert '[任务_2]\n开关=1' in after


def test_toggle_task_only_touches_the_given_account():
    """多账号时只改被指定的那一个"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp, [('12345', '小明'), ('67890', '小红')])
        mgr = AccountManager(tmp)

        mgr.toggle_task('67890', '1')      # 翻开 67890 的任务_1

        a = _read(os.path.join(tmp, 'Config', '12345.ini'))
        b = _read(os.path.join(tmp, 'Config', '67890.ini'))

        # 只看任务_1 那一段（任务_2 在两个文件里本来就是 1）
        a_first = a.split('[任务_2]')[0]
        b_first = b.split('[任务_2]')[0]

        assert '开关=0' in a_first, '不该动 12345 的任务_1'
        assert '开关=1' in b_first, '67890 的任务_1 应当被翻开'


# ──────────────────────────────────────────
#  全局设置
# ──────────────────────────────────────────

def test_global_settings():
    with tempfile.TemporaryDirectory() as tmp:
        _make_game_dir(tmp)
        mgr = AccountManager(tmp)
        assert mgr.get_speed() == 3
        assert mgr.is_muted() is True
        assert mgr.is_auto_confirm() is True


def test_global_settings_defaults_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = AccountManager(tmp)
        assert mgr.get_speed() == 1
        assert mgr.is_muted() is False


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_list_accounts,
        test_list_accounts_when_no_file,
        test_get_account,
        test_list_tasks_only_picks_task_sections,
        test_list_tasks_reads_switch,
        test_task_summary,
        test_toggle_task_flips_the_switch,
        test_toggle_task_preserves_comments,
        test_toggle_task_only_touches_the_given_account,
        test_global_settings,
        test_global_settings_defaults_when_missing,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
        except Exception as e:
            print(f"  💥 {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
