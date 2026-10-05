"""
精灵图鉴 Web 版 —— FastAPI 后端。

启动方式:
    python -m web.app                      # 默认读 ./data
    python -m web.app --data-dir <目录>     # 指定其它目录

或:
    cd seer-toolkit
    uvicorn web.app:create_app --factory --reload

访问: http://127.0.0.1:8000
"""

import sys
import os
import argparse
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.pokedex import Pokedex, _ALLOWED_STATS, _STAT_CN
from database.type_chart import ELEMENT_TYPES, TypeChart

# ──────────────────────────────────────────
#  全局 Pokedex 实例
# ──────────────────────────────────────────
pokedex: Optional[Pokedex] = None


def get_pokedex() -> Pokedex:
    if pokedex is None:
        raise HTTPException(503, "数据库未加载，请用 --data-dir 指定数据目录")
    return pokedex


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
    """创建 FastAPI 应用（工厂函数）"""
    global pokedex

    if data_dir:
        pokedex = Pokedex(data_dir)

    app = FastAPI(
        title="精灵图鉴 Web 版",
        description="基于 SQLite 的赛尔号精灵查询系统",
        version="2.0.0",
    )

    # ── API 路由 ──────────────────────────

    @app.get("/api/monsters/count")
    async def get_count():
        """精灵总数"""
        dex = get_pokedex()
        return {"count": dex.count()}

    @app.get("/api/monsters/stats")
    async def get_stats():
        """获取可用于排序的属性列表"""
        return {
            "stats": [
                {"key": k, "label": v}
                for k, v in _STAT_CN.items()
                if k not in ("ID", "DefName", "Type", "Gender", "IsDark")
            ]
        }

    @app.get("/api/monsters/search")
    async def search(
        q: str = Query(..., min_length=1, description="精灵名称关键词"),
        fields: Optional[str] = Query(None, description="逗号分隔的字段名，只返回这些字段"),
    ):
        """按名称模糊搜索"""
        dex = get_pokedex()
        results = [project_fields(row, fields) for row in dex.search(q)]
        return {"count": len(results), "results": results}

    @app.get("/api/monsters/type")
    async def filter_by_type(
        element: str = Query(..., min_length=1, description="属性名，如 火/水/草/电·火")
    ):
        """按属性筛选（双属性精灵也能被任一属性筛到）"""
        dex = get_pokedex()
        try:
            results = dex.filter_by_type(element)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"count": len(results), "element": element, "results": results}

    # ── 属性克制 ──────────────────────────

    @app.get("/api/types")
    async def list_types():
        """全部单属性"""
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
    async def monster_effectiveness(monster_id: int):
        """某精灵的属性弱点 / 抗性 / 免疫"""
        dex = get_pokedex()
        data = dex.get_type_effectiveness(monster_id)
        if data is None:
            raise HTTPException(404, f"精灵 #{monster_id} 不存在或没有可识别的属性")
        return data

    @app.get("/api/monsters/top")
    async def top_n(
        stat: str = Query(..., description="排序字段"),
        n: int = Query(10, ge=1, le=100, description="返回数量"),
    ):
        """按某属性排名"""
        if stat not in _ALLOWED_STATS:
            raise HTTPException(400, f"无效排序字段: {stat}，可选: {', '.join(_ALLOWED_STATS)}")
        dex = get_pokedex()
        results = dex.top_n(stat, n)
        return {"count": len(results), "stat": stat, "label": _STAT_CN.get(stat, stat), "results": results}

    @app.get("/api/monsters/{monster_id}")
    async def get_monster(
        monster_id: int,
        fields: Optional[str] = Query(
            None, description="逗号分隔的字段名，只返回这些字段，如 ID,DefName,Total"),
    ):
        """精灵详情"""
        dex = get_pokedex()
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
    ):
        """精灵技能列表"""
        dex = get_pokedex()
        moves = dex.get_moves(monster_id, with_effects=effects)
        return {"monster_id": monster_id, "count": len(moves), "moves": moves}

    # ── 静态文件 ──────────────────────────
    static_dir = Path(__file__).parent / "static"
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
    parser.add_argument("--data-dir", default="data",
                        help="雷小伊 data 目录路径 (默认 ./data)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    # 初始化全局 Pokedex
    pokedex = Pokedex(args.data_dir)
    print(f"✅ 数据库已加载: {pokedex.count()} 只精灵")

    app = create_app()  # data_dir 已通过全局变量注入
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
