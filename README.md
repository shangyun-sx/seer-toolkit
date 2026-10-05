# Seer Toolkit

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/shangyun-sx/seer-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/shangyun-sx/seer-toolkit/actions/workflows/ci.yml)

一个从零手写的命令行工具，用于管理赛尔号（Seer）游戏本地数据。项目涵盖四个技术方向：**INI 解析**、**SQLite 操作**、**OpenCV 图像模板匹配**、**FastAPI Web 应用**。

> 这是一个学习项目，代码从零编写，不依赖游戏客户端本身。

## 项目结构

```
seer-toolkit/
├── main.py                    # 入口 -- 交互式命令行菜单
├── requirements.txt           # Python 依赖
├── pyproject.toml             # ruff / pytest 配置 ✨新增
├── .github/workflows/ci.yml   # CI: 代码检查 + 多版本测试 ✨新增
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
│   ├── pokedex.py            #   精灵图鉴查询引擎
│   │                          #   模糊搜索/属性筛选/TopN/跨库关联
│   │                          #   含 SQL 注入防护
│   ├── type_chart.py         #   属性克制系统
│   │                          #   26 单属性 + 138 属性组合
│   │                          #   双属性倍率公式计算/弱点抗性查询
│   ├── effects.py            #   技能效果解析 ✨新增
│   │                          #   2380 条效果模板 + 35 张参数表
│   │                          #   渲染成中文描述，0 异常兜底
│   ├── attributes.py         #   六维属性值对象 ✨新增
│   │                          #   种族值总和，列顺序单一事实来源
│   └── integrity.py          #   MD5 数据库完整性校验
│                               #   含文件名模糊匹配
│
├── web/                       # 学习线四: FastAPI Web 应用
│   ├── __init__.py
│   ├── app.py                #   FastAPI 后端 API
│   └── static/
│       ├── index.html        #   前端页面
│       ├── style.css         #   深色主题 UI
│       └── app.js            #   原生 JS 前端逻辑
│
├── vision/                    # 学习线三: 图像模板匹配
│   ├── __init__.py
│   ├── template_match.py     #   OpenCV 模板匹配核心
│   └── auto_click.py         #   自动点击 (截屏->匹配->点击)
│
├── tests/                     # 测试 (全部离线，不需要游戏数据)
│   ├── __init__.py
│   ├── test_ini_parser.py    #    6 项
│   ├── test_type_chart.py    #   22 项
│   ├── test_effects.py       #   27 项 ✨新增
│   ├── test_attributes.py    #   12 项 ✨新增
│   ├── test_pokedex.py       #   21 项 + SQL注入防护
│   └── test_template_match.py #   2 项合成图像
│
└── data/                      # 游戏本地数据库 (需自行提供)
                               # 已被 .gitignore 排除，不会上传
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备数据：把雷小伊的 data 目录内容放到本项目的 data/ 下
#    （这些文件已被 .gitignore 排除，不会上传到 GitHub）
#    seer-toolkit/data/{Monster.db, Moves.db, ...}

# 3. 命令行版
python main.py

# 4. Web 版
python -m web.app
# 然后打开 http://127.0.0.1:8000
```

数据放在别处时，用 `--data-dir` 指定：

```bash
python main.py --data-dir /path/to/雷小伊          # 会自动接 /data
python -m web.app --data-dir /path/to/雷小伊/data  # 直接指向 data 目录
```

## 功能列表

| 功能 | 对应模块 | 依赖外部数据 |
|------|---------|:---:|
| 查看账号信息 | `config/account_manager.py` | 是 |
| 查看任务统计 | `config/account_manager.py` | 是 |
| 切换任务开关 | `config/ini_parser.py` | 是 |
| 精灵图鉴查询 | `database/pokedex.py` | 是 |
| 属性克制查询 | `database/type_chart.py` | **否** |
| 精灵属性弱点 | `database/pokedex.py` | 是 |
| 技能列表 (含学习等级) | `database/pokedex.py` | 是 |
| 技能效果描述 | `database/effects.py` | 是 |
| 种族值总和排名 | `database/attributes.py` | 是 |
| 校验数据库 MD5 | `database/integrity.py` | 是 |
| 图像模板匹配 | `vision/template_match.py` | 否 |
| 自动点击 | `vision/auto_click.py` | 否 |
| Web 图鉴 | `web/app.py` | 是 |

## 属性克制系统

属性数据建模参考了 [SeerAPI](https://github.com/SeerAPI/seerapi) 的
`ElementType` / `ElementTypeRelation` / `TypeCombination` 三层结构：

| 概念 | 本项目的实现 |
|------|-------------|
| 单属性 | `ELEMENT_TYPES` —— 26 个属性（中文名 + 英文名） |
| 单属性克制倍率 | `_ATTACK_RELATIONS` —— 攻击方 → 防御方，只存非 1 倍项 |
| 属性组合 | `TYPE_COMBINATIONS` —— 138 个组合（26 单属性 + 112 双属性） |

倍率只有 `{0, 0.5, 1, 2}` 四种。**双属性不能简单地把两个单属性倍率相乘**，
赛尔号用的是「拆分后求和再修正」的规则：

```
单打单          直接查表
单打双 / 双打单  拆开双属性得到 x1、x2：
                   x1 == x2 == 2        → 4
                   x1 == 0 或 x2 == 0   → (x1 + x2) / 4
                   其它                 → (x1 + x2) / 2
双打双          拆防守方的两个属性，各算一次「双打单」，再取平均
```

```python
from database.type_chart import TypeChart

TypeChart.multiplier('圣灵·地面', '电·火')   # 4.0
TypeChart.multiplier('次元·电', '地面')      # 0.25
TypeChart.defense_profile('电·火')           # {'weaknesses': [('圣灵', 4.0), ...], ...}
TypeChart.with_stab('电', '电', '水')        # 3.0  —— 含本系加成
```

**数据与公式来源**

- 属性数据：`https://api.seerapi.com/v1/element_type/<id>`
- 双属性公式：[4399《单双属性克制系数计算方法与n属性计算公式猜想》](https://news.4399.com/gonglue/seer/jingyanxinde/825548.html)

数据库里的 `monsters.Type` 存的是**属性组合 ID**（`1~20` 和 `221~226` 是单属性，
`21~132` 是双属性）。所以 `filter_by_type('火')` 会把「火·飞行」这类双属性精灵
也一并筛出来 —— 这是旧版 `Type = ?` 做不到的。

## 技能效果解析

游戏把技能效果拆成三层，和 SeerAPI 的 `SkillEffectType` / `SkillEffectParam` /
`SkillEffectInUse` 是一一对应的：

| 数据 | 位置 | 规模 |
|---|---|---|
| 效果模板 | `EffectInfo.db` → `Effect.info` | 2380 条 |
| 参数取值表 | `EffectInfo.db` → `ParamType.params` | 35 类 |
| 技能挂了哪些效果 | `Moves.db` → `moves.SideEffect` | 25880 / 27307 |
| 效果的具体参数 | `Moves.db` → `moves.SideEffectArg` | — |

`SideEffect` 是**多个效果的顺序列表**，`SideEffectArg` 是按各自 `argsNum`
顺序拼接的参数。渲染就是顺序消费 + 模板取值：

```
钢之爪  SideEffect=4  SideEffectArg='0 20 1'
  effect4 = '技能使用成功时，{1}%改变自身{0}等级{2}'
  {0}=0  → 紧跟「自身…等级」，查六维表 → 攻击
  {1}=20, {2}=1 → 紧跟「等级」是增量，补正号
  → 技能使用成功时，20%改变自身攻击等级+1
```

```python
from database.effects import EffectParser

parser = EffectParser('data')
parser.render_effect(4, ['0', '100', '1'])   # '技能使用成功时，100%改变自身攻击等级+1'
parser.describe('4 5 ', '0 100 1 5 15 -1')   # 多条效果用「；」连起来
```

**参数类型怎么推断**：数据里**没有**「效果 → 参数类型」的映射列，只能从模板措辞
判断。约 90% 的占位符是纯数字，只有约 10% 需要查表：

| 模板特征 | 判定 |
|---|---|
| 后面紧跟「等级」，或「提升…个等级」 | 查六维表 |
| 前面是「令对方 / 使自身…」，且后面不是数量词 | 查异常状态表 |
| 其余 | 直接填数字 |

判断顺序必须**先六维、后状态** —— `使自身{2}提升1个等级` 里的 `{2}` 前缀像状态
（`使自身`）、后缀却是等级，必须判成六维。

**兜底策略**：六维下标越界退回原始数字、状态名查不到原样输出、参数不够显示 `?`、
未知效果 ID 显示 `[未知效果#N]`。**任何情况都不抛异常** —— 全量 25880 个技能
实测 0 异常、100% 有输出。

**数据来源**：本地 `EffectInfo.db` 缺了 213 个 id，其中 5 个被技能引用
（`id=31` 被 303 个技能引用）。这 5 个用 `_SUPPLEMENTAL_EFFECTS` 从
`https://api.seerapi.com/v1/skill_effect_type/<id>` 补齐 —— 已核对 API 与本地的
`argsNum` / `info` 在 17 个抽样 id 上逐字节一致，确认是同一版本。

## 六维属性值对象

体力 / 攻击 / 防御 / 特攻 / 特防 / 速度在数据库里是六个独立的列。封成
`SixAttributes`（`database/attributes.py`）之后，「种族值总和」就有了落点：

```python
from database.attributes import SixAttributes

attrs = SixAttributes.from_row(行)
attrs.total          # 种族值总和
```

`FIELDS` 是列顺序的**单一事实来源** —— 排序用的 SQL 表达式
（`HP + Atk + Def + SpAtk + SpDef + Spd`）由它拼出来，不手写。
`top_n('Total')` 就是靠它排序的。

## 游戏数据库结构备注

在真实的 `雷小伊/data` 上验证过的几个关键点：

`Monster.db` → `monsters`：

| 列 | 说明 |
|---|---|
| `Type` | **属性组合 ID**，不是单属性 ID。全库只有 139 个取值 = 138 个组合 + `0` |
| `Moves` | **JSON 数组**（不是逗号分隔），每项带学习等级 |
| `ID` | `>= 15000` 是皮肤；`>= 1300000` 是载具/道具形态（`Type=0`，无属性） |

`Moves` 的 JSON 结构对应 SeerAPI 的 `SkillInPet`（skill + learning_level）：

```json
[{"ID": 10006, "LearningLv": 1, "Rec": 0, "Tag": 0}, ...]
```

`Moves.db` → `moves`：`Category` 为 `1=物理 / 2=特殊 / 4=属性`。

## API 接口 (Web 版)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/monsters/count` | 精灵总数 |
| GET | `/api/monsters/search?q=雷伊` | 按名称搜索 |
| GET | `/api/monsters/type?element=火` | 按属性筛选（含双属性） |
| GET | `/api/monsters/top?stat=HP&n=10` | 能力排名（`stat` 也可用 `Total` 种族值总和） |
| GET | `/api/monsters/{id}` | 精灵详情 |
| GET | `/api/monsters/{id}/moves` | 技能列表（含学习等级/属性/类别） |
| GET | `/api/monsters/{id}/effectiveness` | 精灵的属性弱点/抗性/免疫 |
| GET | `/api/types` | 全部单属性 |
| GET | `/api/types/effectiveness?element=电·火` | 属性克制关系（打击面 + 防守面） |

两个可选的查询参数 ✨新增：

```bash
# 技能效果描述（默认关，因为要多读一个库）
curl "/api/monsters/70/moves?effects=true"

# 字段投影：精灵对象有 28 列，只要几列时别全量返回
curl "/api/monsters/70?fields=ID,DefName,TypeName,Total"
curl "/api/monsters/search?q=雷伊&fields=DefName,Total"
```

> 浏览器打开后，侧边栏「属性克制」下拉框可以直接查任意属性；点开精灵详情会显示
> 该精灵的弱点、抗性，以及每条技能的效果描述。

## 运行测试

```bash
# 一行跑全部（90 项，全部离线，不需要游戏数据）
python -m pytest tests/ -q

# 也可以单独跑，每个测试文件都带独立入口
python tests/test_ini_parser.py        #  6 项 INI 解析
python tests/test_type_chart.py        # 22 项 属性克制
python tests/test_effects.py           # 27 项 技能效果解析
python tests/test_attributes.py        # 12 项 六维属性
python tests/test_pokedex.py           # 21 项 图鉴 (临时造库)
python tests/test_template_match.py    #  2 项 合成图像匹配

# 需要真实游戏数据库的检查（data/ 被 gitignore，所以不进 pytest）
python tests/test_pokedex.py /path/to/雷小伊目录
python tests/test_effects.py /path/to/雷小伊目录
```

代码检查：

```bash
pip install ruff
ruff check .
```

## 涉及的技术点

- **INI 解析器**：多编码支持（UTF-8/GBK）、有序字典、内存增删改查、文件序列化
- **SQLite 操作**：参数化查询、SQL 注入防护（列名白名单）、跨库关联查询
- **MD5 校验**：分块哈希计算、文件名模糊匹配
- **属性克制算法**：单属性查表 + 双属性拆分公式（不可简单相乘）、字典稀疏存储、贪心最长匹配解析属性名
- **技能效果渲染**：模板占位符替换、从措辞推断参数类型（先六维后状态的判定顺序）、顺序消费参数组、全链路兜底不抛异常
- **JSON 字段解析**：`Moves` 列是带学习等级的 JSON 数组，需容错解析并兼容旧格式
- **值对象**：`@dataclass(frozen=True)` 封装六维属性，`FIELDS` 作为列顺序的单一事实来源
- **OpenCV 模板匹配**：TM_CCOEFF_NORMED 算法、多模板搜索、可视化标注
- **FastAPI Web 应用**：RESTful API 设计、静态文件服务、字段投影、前后端分离架构
- **前端开发**：原生 JS SPA、Fetch API、DOM 操作、CSS Grid/Flexbox 响应式布局
- **工程化**：ruff 静态检查、pytest 离线测试（合成数据库）、GitHub Actions 多版本矩阵

## 致谢

- [SeerAPI](https://github.com/SeerAPI/seerapi) —— 属性建模思路与属性数据来源；技能效果的数据结构（`SkillEffectType` / `SkillEffectParam`）；六维属性值对象；CLI 字段投影
- [4399 赛尔号](https://news.4399.com/gonglue/seer/jingyanxinde/825548.html) —— 双属性克制系数公式

## 许可

MIT License -- 详见 [LICENSE](LICENSE)
