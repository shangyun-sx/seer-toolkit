"""
sqlite 连接的线程管理
=====================

以前 `Pokedex` / `EffectParser` 各自维护**一条**连接，开的时候挂
`check_same_thread=False`。那个开关不是"让连接支持多线程"，只是让 sqlite3
**别抛异常** —— 共享的连接和游标依然会让两个线程读到彼此的中间状态
（`Cursor needed to be reset`），并发写还会撞上 `database is locked`。

这里改成**每个线程一条自己的连接**：互不干扰，读还能真并发。

仍然保留 `check_same_thread=False`，是因为 `close()` 需要在收尾线程里一次性
关掉所有线程开过的连接 —— 连接本身不会被跨线程使用，所以这个开关只是给
收尾开的口子。
"""

import os
import sqlite3
import threading
from typing import Dict, List, Optional


class ThreadLocalConnections:
    """按线程持有 sqlite 连接，并能统一关闭。

        conns = ThreadLocalConnections('data')
        conns.get('Monster.db')     # 当前线程的那条，没有就新开
        conns.close()               # 关掉所有线程开过的
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._local = threading.local()
        # 所有线程开过的连接都登记在这里，close() 才关得全
        self._all: List[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def get(self, filename: str) -> sqlite3.Connection:
        """取当前线程持有的那条连接，没有就新开一条。"""
        # getattr 拿不到时是 None，所以要标成 Optional —— 不标的话 mypy 会
        # 认为「dict 变量被赋了 None」而报错
        cache: Optional[Dict[str, sqlite3.Connection]] = getattr(
            self._local, 'conns', None)
        if cache is None:
            cache = {}
            self._local.conns = cache

        conn = cache.get(filename)
        if conn is None:
            conn = self._open(filename)
            cache[filename] = conn
        return conn

    @staticmethod
    def _tune(conn: sqlite3.Connection) -> None:
        """调一下 SQLite 的两项默认值。

        SQLite 默认页缓存是 2MB，而目录里最小的库都比它大（Monster.db 5.4MB）——
        于是几乎每次查询都要回磁盘。实测：主键查一行也要 25ms，和全表扫描一样，
        因为代价全在「碰文件」这一步，跟查询写得好不好无关。

            默认                23.7 ms
            mmap_size=256MB      0.7 ms
            cache_size=8MB       0.8 ms

        接口层的效果：/api/monsters/search 从 56ms 降到 6ms。

        两个都设，但主次不同：
          * mmap 是主力 —— 页面由 OS 管理、**多条连接共享**，不重复占内存
          * cache_size 是兜底 —— 库放在网络盘之类 mmap 不生效的地方时，
            还不至于退回原速。注意它是**每连接**的，所以只给 8MB 而不是更大
        """
        conn.execute('PRAGMA mmap_size = 268435456')   # 256MB 上限，按文件实际大小映射
        conn.execute('PRAGMA cache_size = -8000')      # 负数的单位是 KB

    def _open(self, filename: str) -> sqlite3.Connection:
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"数据库不存在: {path}")

        # check_same_thread=False 只为 close() 能跨线程收尾（见模块开头）
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row      # 支持字典式访问
        self._tune(conn)
        with self._lock:
            self._all.append(conn)
        return conn

    def open_count(self) -> int:
        """当前还开着的连接数（诊断 / 测试用）"""
        with self._lock:
            return len(self._all)

    def close(self) -> None:
        """关掉所有线程开过的连接。重复调用安全。"""
        with self._lock:
            conns, self._all = self._all, []

        for conn in conns:
            try:
                conn.close()
            except sqlite3.Error:
                # 已经关了 / 正被别的线程占着 —— 收尾阶段不值得再抛
                pass

        # 丢掉各线程的连接记录，下次 get() 会重新开
        self._local = threading.local()
