"""
路径解析
========

打包成 exe 之后，有三件事的语义会变，全都得收在这一处：

  * **工作目录** —— 双击 exe 时它是随机的（可能是 C:\\Windows\\System32），
    所以任何相对路径都不可靠
  * **`__file__`** —— 源码被打进 PyInstaller 的归档，`__file__` 指向
    `sys._MEIPASS` 下的临时解压目录，而不是源码树
  * **数据目录** —— 游戏数据在用户自己磁盘上，得记住用户选过哪个

约定：本项目里说的「数据目录」一律指**包含 Monster.db 的那个目录**
（也就是 `Pokedex` 接收的那个）。雷小伊根目录另有其人，见 `game_dir_of()`。
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

#: 本文件在 config/ 下，所以项目根目录要往上两级。
#: 三种运行方式下它都成立：
#:     源码树        -> <repo>
#:     pip 安装      -> <site-packages>
#:     PyInstaller   -> sys._MEIPASS
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: 应用自己的配置文件名（放在 user_data_dir() 下）
CONFIG_NAME = 'config.json'

#: 用户数据目录的环境变量覆盖。测试靠它避开真实用户目录，
#: 顺带也方便把配置挪到别处。属于公开接口，别改名。
CONFIG_DIR_ENV = 'SEER_CONFIG_DIR'


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打出来的包里"""
    return bool(getattr(sys, 'frozen', False))


def resource_path(*parts: str) -> Path:
    """取打包进来的资源（如 web/static）。

    PyInstaller 会把 datas 解压到 sys._MEIPASS；非打包环境就在包所在的那层。
    两者都是「相对包目录」的，所以同一段代码在三种运行方式下都对。
    """
    base = Path(getattr(sys, '_MEIPASS')) if is_frozen() else _PROJECT_ROOT
    return base.joinpath(*parts)


def user_data_dir() -> Path:
    """放应用自己配置/缓存的地方（不是游戏数据）。

        Windows : %LOCALAPPDATA%\\seer-toolkit
        macOS   : ~/Library/Application Support/seer-toolkit
        其它    : $XDG_DATA_HOME/seer-toolkit 或 ~/.local/share/seer-toolkit

    设了 SEER_CONFIG_DIR 就听它的（测试用，也方便把配置挪到别处）。
    """
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override)

    app = 'seer-toolkit'
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        base = Path(local) if local else Path.home() / 'AppData' / 'Local'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        xdg = os.environ.get('XDG_DATA_HOME')
        base = Path(xdg) if xdg else Path.home() / '.local' / 'share'
    return base / app


def load_user_config() -> dict:
    """读应用配置。文件不存在或内容坏了都当空配置处理 —— 配置文件不该拦住启动。"""
    try:
        raw = (user_data_dir() / CONFIG_NAME).read_bytes()
        config = json.loads(raw.decode('utf-8'))
    except (OSError, ValueError):
        return {}
    return config if isinstance(config, dict) else {}


def save_user_config(config: dict) -> None:
    """写应用配置（目录不存在就建）"""
    path = user_data_dir() / CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                    encoding='utf-8')


def remember_data_dir(data_dir: str) -> None:
    """把数据目录记进用户配置，下次 `resolve_data_dir()` 就能直接命中。

    只在用户**明确指定**过目录时调用 —— 别在解析流程里顺手写盘，
    否则单元测试一跑就把真实用户目录改了。
    """
    config = load_user_config()
    config['data_dir'] = str(Path(data_dir).expanduser().resolve())
    save_user_config(config)


def _default_data_dir() -> str:
    """一点线索都没有时的兜底。

    打包运行时用「exe 同级的 data/」—— 双击 exe 时工作目录是随机的，
    相对路径不可靠；放 exe 旁边既直观又稳定。
    """
    if is_frozen():
        return str(Path(sys.executable).resolve().parent / 'data')
    return 'data'


def resolve_data_dir(explicit: Optional[str] = None, *,
                     default: Optional[str] = None) -> str:
    """解析数据目录，优先级从高到低：

        1. 显式传入（命令行 --data-dir）
        2. 环境变量 SEER_DATA_DIR
        3. 用户配置里记住的那个（见 remember_data_dir）
        4. default，没给就用 _default_data_dir()

    **纯函数，不写任何东西。** 想让用户的选择被记住，自己显式调
    `remember_data_dir()` —— 放在这里会变成「跑个测试就改了用户配置」。
    """
    if explicit:
        return explicit

    from_env = os.environ.get('SEER_DATA_DIR')
    if from_env:
        return from_env

    remembered = load_user_config().get('data_dir')
    if remembered:
        return str(remembered)

    return default if default is not None else _default_data_dir()


def game_dir_of(data_dir: str) -> str:
    """从数据目录推出雷小伊根目录（账号 / 任务配置所在）。

    约定数据目录是 `<根>/data`，所以拿上一级。用户把数据放在别处时，
    命令行用 --game-dir 显式指定。
    """
    return str(Path(data_dir).expanduser().resolve().parent)
