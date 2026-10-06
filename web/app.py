"""
精灵图鉴 Web 版 —— FastAPI 后端。

启动方式:
    python -m web.app                      # 默认读 ./data
    python -m web.app --data-dir <目录>     # 指定其它目录

或（工厂模式，reload / 多 worker 用得上）:
    uvicorn web.app:create_app --factory --reload
    这条没法传参，数据目录用环境变量 SEER_DATA_DIR 指定，默认 ./data

访问: http://127.0.0.1:8000
"""

import sys
import os
import argparse
from contextlib import asynccontextmanager
from typing import Optional

# Windows 下把 stdout / stderr 都改成 UTF-8，理由和 main.py 里那段一样：
#   * 完全不改 —— 输出被重定向或走管道时 Python 退回 GBK，下面那句带 ✅ 的
#     启动提示会直接 UnicodeEncodeError，`python -m web.app > log.txt` 就崩
#   * 只改 stdout —— `2>&1` 会把 UTF-8 和 GBK 混进同一个流
# hasattr 是运行时守卫，不只是为了过类型检查：stdout 被换成没有 reconfigure
# 的对象时（被测试框架接管）硬调会 AttributeError。
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.platform == 'win32' and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi import Depends, FastAPI, Query, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.paths import resource_path, resolve_data_dir
from config.version import __version__
from database.pokedex import Pokedex, ALLOWED_STATS, STAT_CN
from database.type_chart import ELEMENT_TYPES, TypeChart

# 数据目录解析已经搬去 config/paths.py —— 客户端也要用同一套规则，不能再各写一份。
# 这里把名字 import 进来只为不破坏已有调用方（`from web.app import resolve_data_dir`
# 仍然有效）；新代码请直接 import config.paths。


def get_pokedex(request: Request) -> Pokedex:
    """依赖注入：取当前应用自己的 Pokedex。

    以前是模块级全局变量，于是 create_app() 造出来的 app 和全局状态纠缠在
    一起：只有最后一个 app 的参数真正生效，之前造的 app 也会被带着换库。
    放到 `app.state` 之后每个 app 自带一份，互不干扰 —— 这也是 web 层能被
    单独测试的前提（见 tests/test_web_api.py）。
    """
    return request.app.state.pokedex


def project_fields(data: dict, fields: Optional[str]) -> dict:
    """只保留调用方要的字段。

    精灵对象有 28 列，全量返回很浪费。用法: /api/monsters/70?fields=ID,DefName,TypeName

    思路来自 SeerAPI 的 cli/output.py（整个文件才 63 行，核心就是这个函数）。
    """
    if not fields:
        return data
    wanted = {name.strip() for name in fields.split(',') if name.strip()}
    if not wanted:
        return data
    return {key: value for key, value in data.items() if key in wanted}


# ──────────────────────────────────────────
#  FastAPI 应用
# ──────────────────────────────────────────


def create_app(data_dir: str = None) -> FastAPI:
    """创建 FastAPI 应用（工厂函数）。

    每次调用都会建一个**独立的** Pokedex 挂在 `app.state` 上，所以同一个
    进程里可以并存多个读不同数据目录的 app（测试就是这么用的）。
    """
    dex = Pokedex(resolve_data_dir(data_dir))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 关掉 sqlite 连接。桌面客户端会常驻，而在 Windows 上只要还握着
        # 句柄，数据目录就删不掉、换不了。
        yield
        dex.close()

    app = FastAPI(
        title="精灵图鉴 Web 版",
        description="基于 SQLite 的赛尔号精灵查询系统",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.pokedex = dex

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        """HTML / JS / CSS 一律不许浏览器自作主张缓存。

        这几个文件是一起变的：缓存里留着**旧的 index.html**、却拿了**新的
        app.js**，就会出现「JS 找不到新加的 DOM 元素 → 整页渲染中断」，而后端
        全是 200 —— 表象是「数据加载失败」，排查时会一直往接口上找。

        没有 Cache-Control 时浏览器会按启发式规则直接吃缓存、连问都不问。
        加上 no-cache（是「每次要回源校验」，不是「不缓存」）就按 ETag 走 304，
        代价很小。
        """
        response = await call_next(request)
        path = request.url.path
        if path == '/' or path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-cache'
        return response

    # ── API 路由 ──────────────────────────

    @app.get("/api/monsters/count")
    async def get_count(dex: Pokedex = Depends(get_pokedex)):
        """精灵总数"""
        return {"count": dex.count()}

    @app.get("/api/monsters/stats")
    async def get_stats():
        """获取可用于排序的属性列表（纯静态表，不碰数据库）"""
        return {
            "stats": [
                {"key": k, "label": v}
                for k, v in STAT_CN.items()
                if k not in ("ID", "DefName", "Type", "Gender", "IsDark")
            ]
        }

    @app.get("/api/monsters/search")
    async def search(
        q: str = Query(..., min_length=1, description="精灵名称关键词"),
        limit: int = Query(20, ge=1, le=200, description="这一页最多几条"),
        offset: int = Query(0, ge=0, description="跳过前几条"),
        fields: Optional[str] = Query(None, description="逗号分隔的字段名，只返回这些字段"),
        dex: Pokedex = Depends(get_pokedex),
    ):
        """按名称模糊搜索。

        返回里 **total 才是真实总数**，shown 只是这一页有几条。以前只有
        count=len(结果)，前端照着显示「共 N 条」，用户会以为是全部。
        """
        rows = dex.search(q, limit=limit, offset=offset)
        return {
            "total": dex.count_search(q),
            "shown": len(rows),
            "offset": offset,
            "results": [project_fields(row, fields) for row in rows],
        }

    @app.get("/api/monsters/type")
    async def filter_by_type(
        element: str = Query(..., min_length=1, description="属性名，如 火/水/草/电·火"),
        limit: int = Query(50, ge=1, le=200, description="这一页最多几条"),
        offset: int = Query(0, ge=0, description="跳过前几条"),
        dex: Pokedex = Depends(get_pokedex),
    ):
        """按属性筛选（双属性精灵也能被任一属性筛到）"""
        try:
            rows = dex.filter_by_type(element, limit=limit, offset=offset)
            total = dex.count_by_type(element)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {
            "total": total,
            "shown": len(rows),
            "offset": offset,
            "element": element,
            "results": rows,
        }

    # ── 属性克制 ──────────────────────────

    @app.get("/api/types")
    async def list_types():
        """全部单属性（纯静态表，不碰数据库）"""
        return {
            "count": len(ELEMENT_TYPES),
            "types": [
                {"id": tid, "name": cn, "name_en": en}
                for tid, cn, en in TypeChart.all_types()
            ],
        }

    @app.get("/api/types/effectiveness")
    async def type_effectiveness(
        element: str = Query(..., min_length=1, description="属性名，如 火 / 电·火")
    ):
        """某属性的克制关系（打击面 + 防守面）"""
        try:
            label = TypeChart.label(element)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {
            "element": label,
            "offense": TypeChart.offense_profile(element),
            "defense": TypeChart.defense_profile(element),
        }

    @app.get("/api/monsters/{monster_id}/effectiveness")
    async def monster_effectiveness(
        monster_id: int,
        dex: Pokedex = Depends(get_pokedex),
    ):
        """某精灵的属性弱点 / 抗性 / 免疫"""
        data = dex.get_type_effectiveness(monster_id)
        if data is None:
            raise HTTPException(404, f"精灵 #{monster_id} 不存在或没有可识别的属性")
        return data

    @app.get("/api/monsters/top")
    async def top_n(
        stat: str = Query(..., description="排序字段"),
        n: int = Query(10, ge=1, le=100, description="返回数量"),
        dex: Pokedex = Depends(get_pokedex),
    ):
        """按某属性排名"""
        if stat not in ALLOWED_STATS:
            raise HTTPException(400, f"无效排序字段: {stat}，可选: {', '.join(ALLOWED_STATS)}")
        results = dex.top_n(stat, n)
        return {"count": len(results), "stat": stat, "label": STAT_CN.get(stat, stat), "results": results}

    @app.get("/api/monsters/{monster_id}")
    async def get_monster(
        monster_id: int,
        fields: Optional[str] = Query(
            None, description="逗号分隔的字段名，只返回这些字段，如 ID,DefName,Total"),
        dex: Pokedex = Depends(get_pokedex),
    ):
        """精灵详情"""
        monster = dex.get_by_id(monster_id)
        if not monster:
            raise HTTPException(404, f"精灵 #{monster_id} 不存在")
        # 去掉一些不常用的字段
        for key in list(monster.keys()):
            if monster[key] is None:
                monster[key] = ""
        return project_fields(monster, fields)

    @app.get("/api/monsters/{monster_id}/moves")
    async def get_moves(
        monster_id: int,
        effects: bool = Query(False, description="是否解析技能效果描述"),
        dex: Pokedex = Depends(get_pokedex),
    ):
        """精灵技能列表"""
        moves = dex.get_moves(monster_id, with_effects=effects)
        return {"monster_id": monster_id, "count": len(moves), "moves": moves}

    # ── 静态文件 ──────────────────────────
    # 走 resource_path 而不是 Path(__file__).parent —— 打包后 __file__ 指向
    # PyInstaller 解压出的临时目录，前端得按 _MEIPASS 那套去找
    static_dir = resource_path('web', 'static')
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index():
        """前端页面"""
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "前端页面未找到，请确保 web/static/index.html 存在"}

    return app


# ──────────────────────────────────────────
#  直接启动
# ──────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="精灵图鉴 Web 版")
    parser.add_argument("--data-dir", default=None,
                        help="雷小伊 data 目录路径 (默认 ./data 或 $SEER_DATA_DIR)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    if args.reload:
        # reload 要求以 import string 加载应用 —— 传 app 实例的话 uvicorn 会
        # 把 should_reload 静默降级成 False（这个 --reload 以前就是这么失效的）。
        # 工厂模式没法传参，所以数据目录走环境变量。
        os.environ['SEER_DATA_DIR'] = resolve_data_dir(args.data_dir)
        uvicorn.run("web.app:create_app", factory=True,
                    host=args.host, port=args.port, reload=True)
    else:
        app = create_app(args.data_dir)
        print(f"✅ 数据库已加载: {app.state.pokedex.count()} 只精灵")
        uvicorn.run(app, host=args.host, port=args.port)
