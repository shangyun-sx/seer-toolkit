"""
测试路径解析（config/paths.py）。

这些规则决定「数据目录到底指哪儿」。出错的表现是「打包成 exe 后双击打不开」，
本地还复现不出来 —— 所以优先级顺序、以及「解析不写盘」这两条必须有测试盯着。

运行: python -m pytest tests/test_paths.py -v
  或: python tests/test_paths.py
"""

import os
import sys
import tempfile
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import paths


class _isolated_config:
    """把用户配置目录临时指到别处。

    测试**绝对不能**碰真实用户目录 —— 否则跑一次测试就改了人家机器上的配置。
    """

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get(paths.CONFIG_DIR_ENV)
        os.environ[paths.CONFIG_DIR_ENV] = self._tmp.name
        return Path(self._tmp.name)

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop(paths.CONFIG_DIR_ENV, None)
        else:
            os.environ[paths.CONFIG_DIR_ENV] = self._old
        self._tmp.cleanup()
        return False


def _without_env(name: str):
    """临时清掉一个环境变量，用完恢复"""
    class _Ctx:
        def __enter__(self):
            self._old = os.environ.pop(name, None)

        def __exit__(self, *exc):
            if self._old is not None:
                os.environ[name] = self._old
            return False
    return _Ctx()


# ──────────────────────────────────────────
#  优先级
# ──────────────────────────────────────────

def test_explicit_beats_everything():
    with _isolated_config():
        with _without_env('SEER_DATA_DIR'):
            os.environ['SEER_DATA_DIR'] = '/from/env'
            try:
                assert paths.resolve_data_dir('/from/cli') == '/from/cli'
            finally:
                os.environ.pop('SEER_DATA_DIR', None)


def test_env_beats_remembered_config():
    with _isolated_config():
        paths.remember_data_dir('/from/config')
        os.environ['SEER_DATA_DIR'] = '/from/env'
        try:
            assert paths.resolve_data_dir() == '/from/env'
        finally:
            os.environ.pop('SEER_DATA_DIR', None)


def test_remembered_config_beats_default():
    with _isolated_config():
        with _without_env('SEER_DATA_DIR'):
            paths.remember_data_dir('/from/config')
            assert paths.resolve_data_dir() == str(Path('/from/config').resolve())


def test_falls_back_to_default():
    """没有任何线索时，非打包环境退到相对路径 'data'"""
    with _isolated_config():
        with _without_env('SEER_DATA_DIR'):
            assert paths.is_frozen() is False, '单元测试不该被判成打包环境'
            assert paths.resolve_data_dir() == 'data'
            assert paths.resolve_data_dir(default='/custom') == '/custom'


# ──────────────────────────────────────────
#  纯函数：解析过程一行都不许写
# ──────────────────────────────────────────

def test_resolve_never_writes():
    """resolve_data_dir 必须是纯函数。

    「顺手把用户选的目录记下来」放在解析里看着贴心，实际后果是：跑一次单元
    测试就把真实用户目录改了。所以写盘只能是 remember_data_dir 的显式行为。
    """
    with _isolated_config() as cfg_dir:
        with _without_env('SEER_DATA_DIR'):
            paths.resolve_data_dir('/some/where')
            paths.resolve_data_dir()
            leftovers = list(cfg_dir.iterdir())
            assert not leftovers, f'解析过程不该写盘，却多出了: {leftovers}'


def test_remember_round_trip():
    with _isolated_config():
        target = Path(tempfile.gettempdir()) / 'seer-data-round-trip'
        paths.remember_data_dir(str(target))
        assert paths.load_user_config()['data_dir'] == str(target.resolve())


def test_corrupt_config_does_not_block_startup():
    """配置坏了当空配置处理，不许拦住启动"""
    with _isolated_config() as cfg_dir:
        with _without_env('SEER_DATA_DIR'):
            (cfg_dir / paths.CONFIG_NAME).write_text('{ 这不是 json', encoding='utf-8')
            assert paths.load_user_config() == {}
            assert paths.resolve_data_dir() == 'data'


# ──────────────────────────────────────────
#  目录定位
# ──────────────────────────────────────────

def test_user_data_dir_follows_override():
    with _isolated_config() as cfg_dir:
        assert paths.user_data_dir() == cfg_dir


def test_resource_path_finds_the_frontend():
    """resource_path 要定位到打包时会被带上的前端资源"""
    index = paths.resource_path('web', 'static', 'index.html')
    assert index.is_file(), f'找不到前端资源: {index}'


class _frozen:
    """临时把解释器伪装成 PyInstaller 打包环境。

    sys.frozen 和 sys._MEIPASS 是 PyInstaller 在运行时注入的两个标记，
    打包前没法真的验，只能这样模拟。
    """

    def __init__(self, meipass=None):
        self._meipass = meipass

    def __enter__(self):
        self._old_frozen = getattr(sys, 'frozen', None)
        self._old_meipass = getattr(sys, '_MEIPASS', None)
        sys.frozen = True
        if self._meipass is not None:
            sys._MEIPASS = self._meipass
        return self

    def __exit__(self, *exc):
        for name, old in (('frozen', self._old_frozen),
                          ('_MEIPASS', self._old_meipass)):
            if old is None:
                if hasattr(sys, name):
                    delattr(sys, name)
            else:
                setattr(sys, name, old)
        return False


def test_frozen_default_is_next_to_the_exe():
    """打包运行时兜底目录是「exe 同级的 data/」，不是相对当前工作目录。

    这条正是 B4 存在的理由：双击 exe 时 cwd 可能是 C:\\Windows\\System32，
    任何相对路径都不可靠。
    """
    with _isolated_config():
        with _without_env('SEER_DATA_DIR'):
            with _frozen():
                expected = Path(sys.executable).resolve().parent / 'data'
                assert Path(paths.resolve_data_dir()) == expected


def test_resource_path_uses_meipass_when_frozen():
    """打包后资源在 sys._MEIPASS 下，不在源码树里"""
    with tempfile.TemporaryDirectory() as tmp:
        with _frozen(meipass=tmp):
            assert paths.resource_path('web', 'static') == Path(tmp) / 'web' / 'static'


def test_game_dir_is_parent_of_data_dir():
    with tempfile.TemporaryDirectory() as root:
        data = Path(root) / 'data'
        data.mkdir()
        assert paths.game_dir_of(str(data)) == str(Path(root).resolve())


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_explicit_beats_everything,
        test_env_beats_remembered_config,
        test_remembered_config_beats_default,
        test_falls_back_to_default,
        test_resolve_never_writes,
        test_remember_round_trip,
        test_corrupt_config_does_not_block_startup,
        test_user_data_dir_follows_override,
        test_resource_path_finds_the_frontend,
        test_frozen_default_is_next_to_the_exe,
        test_resource_path_uses_meipass_when_frozen,
        test_game_dir_is_parent_of_data_dir,
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
