"""
日志配置。
========

项目里以前只有 print。print 的麻烦在于分不清两件事：

  * **用户要看的输出** —— 菜单、表格、查询结果。它们就是程序的产品
  * **出问题时的诊断信息** —— 异常堆栈、编码降级、连不上库

现在把两者分开：前者继续 print，后者走 logging。

另一个关键点：日志**只往 stderr 打**。stdout 要留给真正的输出，否则

    python main.py search 雷伊 --json | jq .

会把日志行也喂给 jq。这是很多命令行工具踩过的坑。
"""

import logging
import sys
from typing import Optional

from config.paths import user_data_dir

#: --debug 时额外落一份日志文件的名字
LOG_NAME = 'seer-toolkit.log'


def setup_logging(debug: bool = False) -> Optional[object]:
    """配置根 logger。

    默认（非 debug）只把 WARNING 及以上打到 stderr；--debug 时降到 DEBUG，
    并额外写一份文件到用户目录 —— 交互式菜单里出的问题，滚屏一多就找不到了。

    返回日志文件路径（没有则 None），主要是给测试和提示用。
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.WARNING)

    # 重复调用时先清掉旧 handler，免得多跑一次就多打印一份
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(sys.stderr)      # 注意是 stderr，不是 stdout
    stream.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root.addHandler(stream)

    if not debug:
        return None

    path = user_data_dir() / LOG_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s: %(message)s'))
        root.addHandler(file_handler)
    except OSError:
        # 日志写不了不该拦住程序 —— 已经有一个 stderr handler 了
        logging.getLogger(__name__).warning('日志文件写入失败: %s', path)
        return None

    return path
