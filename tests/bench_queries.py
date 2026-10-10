"""
查询性能基准 —— 手动跑，不进 CI。
=================================

**为什么不做成 pytest 用例：记时断言在 CI 上必然 flaky。**

runner 是共享的，负载和磁盘冷热每次都不同；而这里关心的差别（页缓存调优
前后，5ms vs 56ms）在快机器上只有几毫秒的绝对值，阈值定宽了抓不住回归、
定窄了偶发失败 —— 最后要么被人加 sleep 绕过，要么被人整个删掉。

可靠的替代是**把「配置对不对」变成断言**（`test_connections.py` 里的
`test_connections_are_tuned`，完全确定、CI 里跑），**把「快不快」留给人**。
这就是这个脚本的用途：按需跑一次，和下面的基准值对照。

本机基准（Windows，预热后中位，2026-10）：

    /api/monsters/search     ~5 ms
    /api/monsters/type       ~7 ms
    /api/monsters/count      ~3 ms

页缓存调优**之前**这三个分别是 56 / 59 / 29 ms。如果跑出来明显高于上表，
先看 `database/connections.py` 里的 `_tune()` 是不是还在。

用法:
    python tests/bench_queries.py [data 目录]
"""

import os
import statistics
import sys
import time

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient          # noqa: E402
from web.app import create_app                     # noqa: E402

URLS = [
    '/api/monsters/search?q=雷&limit=20',
    '/api/monsters/type?element=火&limit=20',
    '/api/monsters/top?stat=Total&n=10',
    '/api/monsters/count',
    '/api/monsters/70',
    '/api/monsters/70/moves',
]


def main() -> int:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else 'data'
    rounds = 15

    with TestClient(create_app(data_dir)) as client:
        print(f'数据目录: {os.path.abspath(data_dir)}   每项 {rounds} 次，取中位\n')

        for url in URLS:
            try:
                client.get(url)                       # 预热：别把冷启动算进去
            except Exception as e:
                print(f'  {url:<40} 跳过 ({type(e).__name__})')
                continue

            samples = []
            for _ in range(rounds):
                start = time.perf_counter()
                client.get(url)
                samples.append((time.perf_counter() - start) * 1000)

            print(f'  {url.split("?")[0]:<30} 中位 {statistics.median(samples):6.1f} ms'
                  f'   最快 {min(samples):5.1f} ms')

    print('\n和文件开头那份基准对照 —— 高出一大截的话，先查 connections.py 的 _tune()')
    return 0


if __name__ == '__main__':
    sys.exit(main())
