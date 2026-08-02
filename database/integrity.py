"""
数据库完整性校验 —— 用 MD5 验证数据文件是否被篡改或需要更新。

雷小伊在 data/Data.ini 中存储了每个 db 文件的 MD5 哈希值，
启动时比对，发现不匹配则触发更新下载。

注意：Data.ini 里的 key 命名并不严谨，和磁盘上的文件名之间存在
单复数差异(Monsters vs Monster)、大小写差异(mintmark vs MintMarks)、
以及无后缀文件(version)等情况，因此不能简单做 key+.db 的映射。
"""

import hashlib
import os
import sys
from typing import Dict, List, Tuple, Optional
from config.ini_parser import IniParser

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def md5_file(filepath: str) -> str:
    """计算文件的 MD5 哈希值"""
    if not os.path.exists(filepath):
        return ''
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        # 分块读取，避免大文件占用过多内存
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
    return md5.hexdigest()


class IntegrityChecker:
    """数据库完整性校验器"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.checksum_file = os.path.join(data_dir, 'Data.ini')
        self.checksums = IniParser(self.checksum_file) if os.path.exists(self.checksum_file) else IniParser()

        # 建立 "标准化名称 -> 实际文件名" 的映射
        # 例如: 'monsters' -> 'Monster.db', 'version' -> 'version'
        self._file_map: Optional[Dict[str, str]] = None

    # ──────────────────────────────────────────
    #  文件名模糊匹配
    # ──────────────────────────────────────────

    def _build_file_map(self) -> Dict[str, str]:
        """
        扫描 data 目录，建立 标准化key -> 实际文件名 的映射。

        标准化规则：取文件名去掉后缀的部分，转小写。
        这样就可以处理:
          Data.ini 写 Monsters  ->  磁盘上是 Monster.db
          Data.ini 写 mintmark ->  磁盘上是 MintMarks.db
          Data.ini 写 version  ->  磁盘上是 version (无后缀)
        """
        if self._file_map is not None:
            return self._file_map

        file_map = {}
        for fname in os.listdir(self.data_dir):
            # 跳过 Data.ini 自身
            if fname == 'Data.ini':
                continue
            full_path = os.path.join(self.data_dir, fname)
            # 只处理文件，跳过目录
            if not os.path.isfile(full_path):
                continue
            # 去掉后缀，转小写，作为标准化名称
            normalized = os.path.splitext(fname)[0].lower()
            file_map[normalized] = fname

        self._file_map = file_map
        return file_map

    def _find_file(self, key: str) -> Optional[str]:
        """
        根据 Data.ini 里的 key，找到磁盘上对应的文件名。

        匹配优先级:
          1. key + '.db' 精确匹配
          2. key 本身精确匹配 (无后缀文件)
          3. key 小写 在标准化映射中查找
        """
        # 1. 尝试 key.db
        candidate = key + '.db'
        if os.path.exists(os.path.join(self.data_dir, candidate)):
            return candidate

        # 2. 尝试 key 原样 (处理 version 这种无后缀文件)
        if os.path.exists(os.path.join(self.data_dir, key)):
            return key

        # 3. 标准化后模糊匹配
        file_map = self._build_file_map()
        normalized_key = key.lower()
        if normalized_key in file_map:
            return file_map[normalized_key]

        # 4. 部分匹配：key 是文件名的一部分 (如 mintmark 包含在 mintmarks 中)
        for norm_name, real_name in file_map.items():
            if normalized_key in norm_name or norm_name in normalized_key:
                return real_name

        return None

    # ──────────────────────────────────────────
    #  哈希值读取
    # ──────────────────────────────────────────

    def get_expected_checksums(self) -> Dict[str, str]:
        """
        读取 Data.ini 中记录的期望哈希值。

        返回: { 'Achievement': 'f5c0d3c3...', 'Moves': '26f1b662...', ... }
        """
        result = {}
        if self.checksums.has_section('Config'):
            for key, value in self.checksums.items('Config'):
                result[key] = value
        return result

    def get_actual_checksums(self) -> Dict[str, str]:
        """
        扫描 data 目录，计算所有数据文件的当前哈希值。

        返回: { 'Achievement': 'f7985248...', 'Monster': '...', ... }
               key 为 Data.ini 风格的名称（尽量保持一致）
        """
        result = {}
        for fname in os.listdir(self.data_dir):
            if fname == 'Data.ini':
                continue
            full_path = os.path.join(self.data_dir, fname)
            if not os.path.isfile(full_path):
                continue
            # key 取去掉后缀的文件名（保留原始大小写）
            key = os.path.splitext(fname)[0]
            result[key] = md5_file(full_path)
        return result

    # ──────────────────────────────────────────
    #  校验逻辑
    # ──────────────────────────────────────────

    def verify(self) -> Tuple[bool, List[Dict], List[Dict]]:
        """
        校验所有登记在 Data.ini 中的数据文件。

        返回: (全部通过?, [匹配项], [异常项])
        每项为 dict: {key, expected_md5, actual_md5, filename, status}
        """
        expected = self.get_expected_checksums()
        actual = self.get_actual_checksums()
        file_map = self._build_file_map()

        matched = []
        mismatched = []

        for key, expected_hash in expected.items():
            # 找到磁盘上的实际文件
            actual_fname = self._find_file(key)

            if actual_fname is None:
                # key 在 Data.ini 里登记了但磁盘上没有对应文件
                mismatched.append({
                    'key': key,
                    'filename': f'{key}.db 或 {key}',
                    'expected_md5': expected_hash,
                    'actual_md5': None,
                    'status': '文件不存在',
                })
                continue

            # 计算实际文件的 MD5
            actual_key = os.path.splitext(actual_fname)[0]
            actual_hash = actual.get(actual_key, '')

            if not actual_hash:
                actual_hash = md5_file(os.path.join(self.data_dir, actual_fname))

            if actual_hash == expected_hash:
                matched.append({
                    'key': key,
                    'filename': actual_fname,
                    'expected_md5': expected_hash,
                    'actual_md5': actual_hash,
                    'status': '匹配',
                })
            else:
                mismatched.append({
                    'key': key,
                    'filename': actual_fname,
                    'expected_md5': expected_hash,
                    'actual_md5': actual_hash,
                    'status': '哈希不匹配',
                })

        # 检查磁盘上有但 Data.ini 未登记的文件
        registered_keys_lower = {k.lower() for k in expected.keys()}
        for fname in os.listdir(self.data_dir):
            if fname == 'Data.ini':
                continue
            full_path = os.path.join(self.data_dir, fname)
            if not os.path.isfile(full_path):
                continue
            key = os.path.splitext(fname)[0]
            # 检查是否没有任何 Data.ini key 能匹配到这个文件
            found = False
            for reg_key in expected.keys():
                if self._find_file(reg_key) == fname:
                    found = True
                    break
            if not found:
                mismatched.append({
                    'key': key,
                    'filename': fname,
                    'expected_md5': None,
                    'actual_md5': md5_file(full_path),
                    'status': '未在 Data.ini 中登记',
                })

        all_ok = len(mismatched) == 0
        return all_ok, matched, mismatched

    def print_report(self) -> None:
        """打印校验报告"""
        ok, matched, mismatched = self.verify()

        print("\n" + "=" * 60)
        print("  数据库完整性校验报告")
        print("=" * 60)

        if matched:
            for m in matched:
                fname = m['filename']
                print(f"  [OK] {fname}")

        if mismatched:
            for m in mismatched:
                fname = m['filename']
                status = m['status']
                if m['expected_md5'] and m['actual_md5']:
                    print(f"  [!!] {fname} ({status})")
                    print(f"       期望: {m['expected_md5'][:16]}...")
                    print(f"       实际: {m['actual_md5'][:16]}...")
                elif m['expected_md5']:
                    # 文件不存在
                    print(f"  [!!] {fname} ({status})")
                else:
                    # 未登记
                    print(f"  [??] {fname} ({status})")

        print("-" * 60)
        if ok:
            print(f"  结果: [OK] 全部通过 ({len(matched)} 个文件)")
        else:
            print(f"  结果: [!!] {len(mismatched)} 个异常, "
                  f"{len(matched)} 个正常 (数据可能已更新)")


# ──────────────────────────────────────────
#  独立运行
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else 'data'
    checker = IntegrityChecker(data_dir)
    checker.print_report()
