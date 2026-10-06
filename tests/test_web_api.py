"""
测试 FastAPI 层（用临时库，不需要游戏数据）。

web/app.py 以前用**模块级全局变量**装 Pokedex，于是 create_app() 造出来的
app 和全局状态纠缠在一起：只有最后一个 app 的参数真正生效，先前造的 app 会被
带着换库；而不传参数的 create_app()（也就是文档里 `--factory` 那条）永远是
503。下面前两个测试专门盯住这两点。

运行: python -m pytest tests/test_web_api.py -v
  或: python tests/test_web_api.py
"""

import os
import sqlite3
import sys
import tempfile

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient

from web.app import create_app

# ID, 名称, Type, HP, Atk, Def, SpAtk, SpDef, Spd
_FAKE_MONSTERS = [
    (1, '雷伊', 5, 70, 120, 80, 110, 80, 130),
    (2, '火猴', 3, 60, 100, 70, 100, 70, 90),
]


def _make_fake_db(data_dir, monsters):
    """在 data_dir 下造一个最小的 Monster.db"""
    conn = sqlite3.connect(os.path.join(data_dir, 'Monster.db'))
    conn.execute(
        "CREATE TABLE monsters (ID INTEGER PRIMARY KEY, DefName TEXT, Type INTEGER, "
        "HP INTEGER, Atk INTEGER, Def INTEGER, SpAtk INTEGER, SpDef INTEGER, Spd INTEGER)"
    )
    conn.executemany("INSERT INTO monsters VALUES (?,?,?,?,?,?,?,?,?)", monsters)
    conn.commit()
    conn.close()


# ──────────────────────────────────────────
#  隔离性 —— 这两条是这次重构的核心
# ──────────────────────────────────────────

def test_two_apps_do_not_share_state():
    """两个 app 各读各的库，互不串味。

    旧实现里 Pokedex 是模块级全局：第二个 create_app() 会把它覆盖掉，
    于是第一个 app 也开始返回第二个库的数据 —— 这里的断言会挂。
    """
    with tempfile.TemporaryDirectory() as dir_a, \
            tempfile.TemporaryDirectory() as dir_b:
        _make_fake_db(dir_a, _FAKE_MONSTERS)            # 2 只
        _make_fake_db(dir_b, _FAKE_MONSTERS[:1])        # 1 只

        app_a = create_app(dir_a)
        app_b = create_app(dir_b)

        # 故意先建两个 app，再依次发请求 —— 顺序反过来一样能过
        with TestClient(app_a) as client_a, TestClient(app_b) as client_b:
            assert client_a.get('/api/monsters/count').json()['count'] == 2
            assert client_b.get('/api/monsters/count').json()['count'] == 1
            # 再问一次 a：如果被 b 覆盖过，这里会变成 1
            assert client_a.get('/api/monsters/count').json()['count'] == 2


def test_factory_without_args_still_works():
    """不传参数造 app 也要能用 —— 文档里 `--factory` 走的就是这条。

    旧实现里 create_app() 不传参 -> 全局还是 None -> 每个接口 503。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_db(tmp, _FAKE_MONSTERS)
        os.environ['SEER_DATA_DIR'] = tmp
        try:
            app = create_app()          # 刻意不给 data_dir
            with TestClient(app) as client:
                resp = client.get('/api/monsters/count')
            assert resp.status_code == 200, resp.text
            assert resp.json()['count'] == 2
        finally:
            os.environ.pop('SEER_DATA_DIR', None)


# ──────────────────────────────────────────
#  接口行为（以前完全没测过）
# ──────────────────────────────────────────

def test_search_and_field_projection():
    """搜索 + fields 字段投影"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_db(tmp, _FAKE_MONSTERS)
        with TestClient(create_app(tmp)) as client:
            data = client.get('/api/monsters/search', params={'q': '雷'}).json()
            assert [r['DefName'] for r in data['results']] == ['雷伊']

            row = client.get('/api/monsters/search',
                             params={'q': '雷', 'fields': 'ID,DefName'}).json()['results'][0]
            assert set(row) == {'ID', 'DefName'}, f'字段投影没生效: {row}'


def test_bad_input_never_reaches_the_database():
    """非法输入要么 400 要么 404/422，不能 500"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_db(tmp, _FAKE_MONSTERS)
        with TestClient(create_app(tmp)) as client:
            # 排序字段白名单（就是那道 SQL 注入防线）
            assert client.get('/api/monsters/top',
                              params={'stat': 'HP; DROP TABLE monsters'}).status_code == 400
            # n 越界由 FastAPI 的 Query(ge=1, le=100) 挡下
            assert client.get('/api/monsters/top',
                              params={'stat': 'HP', 'n': 999}).status_code == 422
            # 不存在的精灵
            assert client.get('/api/monsters/9999').status_code == 404
            # 认不出的属性
            assert client.get('/api/types/effectiveness',
                              params={'element': '不存在的属性'}).status_code == 400


def test_bad_input_does_not_corrupt_the_database():
    """白名单被绕过的话，这条会挂 —— 它确认表还在"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_db(tmp, _FAKE_MONSTERS)
        with TestClient(create_app(tmp)) as client:
            client.get('/api/monsters/top', params={'stat': 'HP; DROP TABLE monsters'})
            assert client.get('/api/monsters/count').json()['count'] == 2


def test_static_routes_do_not_need_a_database():
    """/api/types 和 /api/monsters/stats 是纯静态表，没有数据库也该能用"""
    with TestClient(create_app()) as client:
        assert client.get('/api/types').json()['count'] == 26
        assert client.get('/api/monsters/stats').status_code == 200


def test_shutdown_closes_the_pokedex():
    """退出 lifespan 要把连接关掉（Windows 上不关会锁住数据目录）"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_fake_db(tmp, _FAKE_MONSTERS)
        app = create_app(tmp)
        dex = app.state.pokedex

        with TestClient(app) as client:
            client.get('/api/monsters/count')      # 先建立真实连接
            assert dex.open_connections() > 0

        # 退出 with 之后 lifespan 的收尾应当已经跑过
        assert dex.open_connections() == 0


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_two_apps_do_not_share_state,
        test_factory_without_args_still_works,
        test_search_and_field_projection,
        test_bad_input_never_reaches_the_database,
        test_bad_input_does_not_corrupt_the_database,
        test_static_routes_do_not_need_a_database,
        test_shutdown_closes_the_pokedex,
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
