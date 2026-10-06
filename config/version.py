"""
版本号的**唯一来源**。
=====================

以前这个数字散在三处，互不相同：

    pyproject.toml   version = "0.1.0"
    web/app.py       version="2.0.0"     （FastAPI 的文档页上显示）
    main.py          雷小伊配置管理器 v1.0

改动版本时漏改一处，用户看到的就是三个不同的版本号。现在都从这里读：
pyproject 那边用 setuptools 的 `attr` 指向本模块（走 AST 解析，不需要真
导入），代码里就 `from config.version import __version__`。
"""

__version__ = '0.1.0'
