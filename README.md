# Seer Toolkit

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

一个从零手写的命令行工具，用于管理赛尔号（Seer）游戏本地数据。项目涵盖三个入门级技术方向：**INI 解析**、**SQLite 操作**、**OpenCV 图像模板匹配**。

> 这是一个学习项目，代码从零编写，不依赖游戏客户端本身。

## 项目结构

```
seer-toolkit/
├── main.py                    # 入口 -- 交互式命令行菜单
├── requirements.txt           # Python 依赖
├── .gitignore
├── LICENSE
├── README.md
│
├── config/                    # 学习线一: INI 配置解析
│   ├── __init__.py
│   ├── ini_parser.py         #   手写 INI 解析器 (~220 行)
│   │                          #   支持多编码/增删改查/保持顺序
│   └── account_manager.py    #   账号与任务配置管理
│
├── database/                  # 学习线二: SQLite 数据库
│   ├── __init__.py
│   ├── pokedex.py            #   精灵图鉴查询器
│   │                          #   模糊搜索/属性筛选/TopN/跨库关联
│   │                          #   含 SQL 注入防护
│   └── integrity.py          #   MD5 数据库完整性校验
│                               #   含文件名模糊匹配
│
├── vision/                    # 学习线三: 图像模板匹配
│   ├── __init__.py
│   ├── template_match.py     #   OpenCV 模板匹配核心
│   └── auto_click.py         #   自动点击 (截屏->匹配->点击)
│
├── tests/                     # 测试 (部分可脱离外部数据运行)
│   ├── __init__.py
│   ├── test_ini_parser.py    #   6 项测试
│   ├── test_pokedex.py       #   含 SQL 注入防护验证
│   └── test_template_match.py #  合成图像验证
│
└── data/                      # 游戏本地数据库 (需自行提供)
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行交互菜单 (指定游戏数据目录)
python main.py --data-dir /path/to/game/data

# 3. 或者，不依赖外部数据运行测试
python tests/test_ini_parser.py
python tests/test_template_match.py
```

## 功能列表

| 功能 | 对应模块 | 依赖外部数据 |
|------|---------|:---:|
| 查看账号信息 | `config/account_manager.py` | 是 |
| 查看任务统计 | `config/account_manager.py` | 是 |
| 切换任务开关 | `config/ini_parser.py` | 是 |
| 精灵图鉴查询 | `database/pokedex.py` | 是 |
| 校验数据库 MD5 | `database/integrity.py` | 是 |
| 图像模板匹配 | `vision/template_match.py` | 否 |
| 自动点击 | `vision/auto_click.py` | 否 |

## 运行测试

```bash
# 不需要外部数据
python tests/test_ini_parser.py        # 6 项 INI 解析测试
python tests/test_template_match.py    # 合成图像匹配测试

# 需要游戏数据库
python tests/test_pokedex.py /path/to/game/data
```

## 涉及的技术点

- **INI 解析器**：多编码支持（UTF-8/GBK）、有序字典、内存增删改查、文件序列化
- **SQLite 操作**：参数化查询、SQL 注入防护（列名白名单）、跨库关联查询
- **MD5 校验**：分块哈希计算、文件名模糊匹配
- **OpenCV 模板匹配**：TM_CCOEFF_NORMED 算法、多模板搜索、可视化标注
- **pyautogui 自动化**：屏幕截图、鼠标点击、循环监控

## 许可

MIT License -- 详见 [LICENSE](LICENSE)
