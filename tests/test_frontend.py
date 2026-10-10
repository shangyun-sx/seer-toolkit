"""
跑前端逻辑测试（tests/frontend_dom.mjs）。

为什么用 pytest 包一层去跑 node，而不是让 CI 多加一条命令：

  * **出口只有一个** —— `pytest tests/` 就覆盖了前端，不用记第二条命令；
    覆盖率门槛、CI 的步骤也都不用动
  * 前端测试的文件名不是 test_*.py，pytest 不会误收它，各跑各的

没装 node 就跳过 —— 前端测试不该成为「跑 Python 测试」的前提条件。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / 'frontend_dom.mjs'
NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='没装 node —— 前端逻辑测试需要它')
def test_frontend_logic():
    """前端的纯逻辑：转义、分页计算、URL 拼装、滚动策略、导航与恢复的分支"""
    result = subprocess.run(
        [NODE, str(HARNESS)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )

    assert result.returncode == 0, (
        '前端逻辑测试失败：\n'
        + (result.stdout or '')
        + (result.stderr or '')
    )


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    if NODE is None:
        print('  跳过：没装 node')
    else:
        proc = subprocess.run([NODE, str(HARNESS)])
        raise SystemExit(proc.returncode)
