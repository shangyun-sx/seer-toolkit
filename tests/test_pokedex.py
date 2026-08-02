"""
测试精灵图鉴查询器。

⚠️ 这些测试需要连接到雷小伊的 data/*.db 数据库。
运行时请指定数据目录:
    python tests/test_pokedex.py <雷小伊目录>
"""

import os
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.pokedex import Pokedex


def test_pokedex(data_dir: str):
    """测试基本查询"""
    dex = Pokedex(data_dir)

    # 精灵总数
    count = dex.count()
    print(f"  精灵总数: {count}")
    assert count > 0, "数据库应该有精灵数据"

    # 按名字搜索
    results = dex.search('雷伊')
    print(f"  搜索 '雷伊': {len(results)} 条结果")
    for r in results:
        print(f"    #{r['ID']} {r['DefName']} ({r['Type']})")

    # 按属性筛选
    fire = dex.filter_by_type('火')
    print(f"  火系精灵: {len(fire)} 条 (显示前3)")
    for r in fire[:3]:
        print(f"    #{r['ID']} {r['DefName']}")

    # Top N
    top = dex.top_n('HP', 5)
    print(f"  血量 Top 5:")
    for r in top:
        print(f"    #{r['ID']} {r['DefName']} HP={r['HP']}")

    # SQL 注入防护测试
    try:
        dex.top_n('HP; DROP TABLE monsters;--', 5)
        print("  ❌ 应抛出异常!")
        assert False
    except ValueError:
        print("  ✅ SQL注入防护正常")

    dex.close()


def test_sql_injection():
    """测试 SQL 注入防护"""
    dex = Pokedex('.')
    try:
        dex.top_n("1; DROP TABLE monsters;--")
        assert False, "应该抛出异常"
    except ValueError as e:
        assert '不允许' in str(e)
        print(f"  ✅ 正确拦截: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python test_pokedex.py <雷小伊目录>")
        print("示例: python test_pokedex.py ../..")
        sys.exit(1)

    data_dir = os.path.join(sys.argv[1], 'data')
    test_pokedex(data_dir)
    test_sql_injection()
