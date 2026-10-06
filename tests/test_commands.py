"""
测试非交互式子命令（cli/commands.py）和日志配置（config/logsetup.py）。

这两块是一起的：命令要能被脚本调用、能 `--json | jq`，所以日志必须走
stderr —— 否则日志行会混进 stdout 把 JSON 弄坏。test_logs_go_to_stderr_
not_stdout 就是钉住这一条。

运行: python -m pytest tests/test_commands.py -v
  或: python tests/test_commands.py
"""

import io
import json
import logging
import os
import sqlite3
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cli import commands
from config.logsetup import setup_logging
from database.pokedex import Pokedex

# ID, 名称, Type, HP, Atk, Def, SpAtk, SpDef, Spd
_MONSTERS = [
    (1, '雷伊', 5, 70, 120, 80, 110, 80, 130),
    (2, '雷神', 5, 90, 130, 90, 120, 90, 140),
    (3, '火猴', 3, 60, 100, 70, 100, 70, 90),
]


def _make_db(data_dir, monsters):
    conn = sqlite3.connect(os.path.join(data_dir, 'Monster.db'))
    conn.execute(
        "CREATE TABLE monsters (ID INTEGER PRIMARY KEY, DefName TEXT, Type INTEGER, "
        "HP INTEGER, Atk INTEGER, Def INTEGER, SpAtk INTEGER, SpDef INTEGER, Spd INTEGER)"
    )
    conn.executemany("INSERT INTO monsters VALUES (?,?,?,?,?,?,?,?,?)", monsters)
    conn.commit()
    conn.close()


class _run:
    """跑一个命令，把 stdout / stderr 和退出码收集起来"""

    def __init__(self, fn, *args, **kwargs):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        with redirect_stdout(self.stdout), redirect_stderr(self.stderr):
            self.code = fn(*args, **kwargs)

    @property
    def out(self):
        return self.stdout.getvalue()

    @property
    def err(self):
        return self.stderr.getvalue()


class _dex:
    """临时库 + Pokedex，退出时收拾干净"""

    def __init__(self, monsters=_MONSTERS):
        self._tmp = tempfile.TemporaryDirectory()
        _make_db(self._tmp.name, monsters)
        self.dex = Pokedex(self._tmp.name)

    def __enter__(self):
        return self.dex

    def __exit__(self, *exc):
        self.dex.close()
        self._tmp.cleanup()
        return False


# ──────────────────────────────────────────
#  命令：JSON 输出
# ──────────────────────────────────────────

def test_search_json():
    with _dex() as dex:
        r = _run(commands.search, dex, '雷', 20, True)
    assert r.code == 0
    data = json.loads(r.out)
    assert data['total'] == 2
    assert data['shown'] == 2
    assert {x['DefName'] for x in data['results']} == {'雷伊', '雷神'}


def test_search_respects_limit():
    with _dex() as dex:
        r = _run(commands.search, dex, '雷', 1, True)
    data = json.loads(r.out)
    assert data['total'] == 2, 'total 是真实总数，不受 limit 影响'
    assert data['shown'] == 1


def test_search_text_output():
    with _dex() as dex:
        r = _run(commands.search, dex, '雷', 20, False)
    assert r.code == 0
    assert '雷伊' in r.out
    assert r.err == '', '正常路径不该往 stderr 写东西'


def test_by_type_json():
    with _dex() as dex:
        r = _run(commands.by_type, dex, '电', 50, True)
    data = json.loads(r.out)
    assert data['total'] == 2
    assert {x['DefName'] for x in data['results']} == {'雷伊', '雷神'}


def test_by_type_unknown_element_fails():
    """认不出的属性：写 stderr 并返回非零，stdout 保持干净"""
    with _dex() as dex:
        r = _run(commands.by_type, dex, '不存在的属性', 50, True)
    assert r.code == 1
    assert r.out == '', 'stdout 必须是干净的，否则 --json 管道会收到垃圾'
    assert '无法识别' in r.err or '属性' in r.err


def test_top_json():
    with _dex() as dex:
        r = _run(commands.top, dex, 'HP', 2, True)
    data = json.loads(r.out)
    assert data['count'] == 2
    assert data['results'][0]['HP'] >= data['results'][1]['HP']


def test_top_bad_stat_fails():
    with _dex() as dex:
        r = _run(commands.top, dex, 'HP; DROP TABLE monsters', 2, True)
    assert r.code == 1
    assert r.out == ''


def test_effectiveness_by_type_name():
    r = _run(commands.effectiveness, None, '火', True)
    assert r.code == 0
    data = json.loads(r.out)
    assert data['element'] == '火'
    assert 'offense' in data and 'defense' in data


def test_effectiveness_by_monster_id():
    with _dex() as dex:
        r = _run(commands.effectiveness, dex, '1', True)
    assert r.code == 0
    data = json.loads(r.out)
    assert data['id'] == 1
    assert data['label'] == '电'


def test_effectiveness_missing_monster_fails():
    with _dex() as dex:
        r = _run(commands.effectiveness, dex, '99999', True)
    assert r.code == 1
    assert r.out == ''


def test_list_types_needs_no_database():
    r = _run(commands.list_types, True)
    assert r.code == 0
    data = json.loads(r.out)
    assert data['count'] == 26
    assert any(t['name'] == '草' for t in data['types'])


def test_list_types_text_output():
    r = _run(commands.list_types, False)
    assert r.code == 0
    assert '草' in r.out


# ──────────────────────────────────────────
#  日志
# ──────────────────────────────────────────

def _strip_our_handlers(before):
    """移除并**关闭**本次测试新加的 handler。

    只动新增的 —— pytest 自己也挂 handler 做日志捕获，关了它就出问题了。
    之所以必须 close：文件 handler 不关的话句柄还开着，Windows 上临时目录
    就删不掉（和数据库连接那个坑是同一回事）。
    """
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
    for handler in before:
        if handler not in root.handlers:
            root.addHandler(handler)


def test_logs_go_to_stderr_not_stdout():
    """关键性质：日志走 stderr。

    走 stdout 的话 `python main.py search 雷伊 --json | jq .` 会因为日志行
    解析失败 —— 命令行工具常见的坑，专门钉一条。

    注意 setup_logging 要在 redirect 里面调：StreamHandler 是在构造时绑定
    sys.stderr 的，先建 handler 再重定向就绑到老对象上去了。
    """
    before = logging.getLogger().handlers[:]
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            setup_logging(debug=False)
            logging.getLogger('测试').warning('注意这里')

        assert out.getvalue() == '', f'日志跑到 stdout 了: {out.getvalue()!r}'
        assert '注意这里' in err.getvalue()
    finally:
        _strip_our_handlers(before)


def test_setup_logging_defaults_to_warning():
    before = logging.getLogger().handlers[:]
    try:
        assert setup_logging(debug=False) is None, '非 debug 不写日志文件'
        assert logging.getLogger().level == logging.WARNING
    finally:
        _strip_our_handlers(before)


def test_setup_logging_debug_writes_a_file():
    """--debug 时额外落一份文件到用户目录（用 SEER_CONFIG_DIR 指到临时目录）"""
    before = logging.getLogger().handlers[:]
    old_env = os.environ.get('SEER_CONFIG_DIR')
    try:
        with tempfile.TemporaryDirectory() as cfg:
            os.environ['SEER_CONFIG_DIR'] = cfg
            path = setup_logging(debug=True)
            assert path is not None

            logging.getLogger('测试').error('落盘了吗')
            for handler in logging.getLogger().handlers:
                handler.flush()

            with open(path, encoding='utf-8') as f:
                assert '落盘了吗' in f.read()

            # 关掉文件 handler，否则下面的临时目录清理会 PermissionError
            _strip_our_handlers(before)
    finally:
        _strip_our_handlers(before)
        if old_env is None:
            os.environ.pop('SEER_CONFIG_DIR', None)
        else:
            os.environ['SEER_CONFIG_DIR'] = old_env


def test_setup_logging_is_idempotent():
    """重复调用不会叠加 handler（否则每跑一次多打印一份）"""
    before = logging.getLogger().handlers[:]
    try:
        setup_logging(debug=False)
        n1 = len(logging.getLogger().handlers)
        setup_logging(debug=False)
        assert len(logging.getLogger().handlers) == n1
    finally:
        _strip_our_handlers(before)


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_search_json,
        test_search_respects_limit,
        test_search_text_output,
        test_by_type_json,
        test_by_type_unknown_element_fails,
        test_top_json,
        test_top_bad_stat_fails,
        test_effectiveness_by_type_name,
        test_effectiveness_by_monster_id,
        test_effectiveness_missing_monster_fails,
        test_list_types_needs_no_database,
        test_list_types_text_output,
        test_logs_go_to_stderr_not_stdout,
        test_setup_logging_defaults_to_warning,
        test_setup_logging_debug_writes_a_file,
        test_setup_logging_is_idempotent,
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
