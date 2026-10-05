"""
INI 文件解析器 —— 手写实现，不依赖第三方库。

支持特性:
- 节 (Section): [节名]
- 键值对: key=value
- 注释: 以 ; 或 # 开头的行为注释
- 保留原始顺序 (基于 OrderedDict)
- GBK / UTF-8 编码自动处理

使用示例:
    parser = IniParser('account.ini')
    print(parser.get('329042484', 'pass'))
    parser.set('329042484', 'nick', '新昵称')
    parser.save()
"""

import re
import os
from collections import OrderedDict
from typing import Optional, List, Tuple, Dict


class IniParser:
    """INI 文件读写器"""

    def __init__(self, filepath: str = None):
        """
        初始化解析器。
        filepath: INI 文件路径，如果文件存在则立即加载
        """
        # 使用有序字典，保持 sections 和 keys 的原始顺序
        self._data: Dict[str, OrderedDict] = OrderedDict()
        # 记录每个 section 中键的顺序
        self._section_order: List[str] = []
        self._filepath = filepath
        # 存储原始行信息，用于保留注释 (可选)
        self._raw_lines: Optional[List[str]] = None

        if filepath and os.path.exists(filepath):
            self.load(filepath)

    # ──────────────────────────────────────────
    #  解析 (反序列化)
    # ──────────────────────────────────────────

    def load(self, filepath: str) -> None:
        """从文件加载并解析 INI 内容"""
        self._filepath = filepath
        self._data.clear()
        self._section_order.clear()

        # 尝试多种编码
        content = self._read_with_encoding(filepath)

        current_section = None
        for line in content.splitlines():
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith(';') or line.startswith('#'):
                continue

            # 匹配节: [SectionName]
            section_match = re.match(r'^\[(.+)\]$', line)
            if section_match:
                current_section = section_match.group(1).strip()
                if current_section not in self._data:
                    self._data[current_section] = OrderedDict()
                    self._section_order.append(current_section)
                continue

            # 匹配键值对: key=value
            kv_match = re.match(r'^([^=]+)=(.*)$', line)
            if kv_match and current_section is not None:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                self._data[current_section][key] = value

    def _read_with_encoding(self, filepath: str) -> str:
        """尝试用多种编码读取文件，优先 UTF-8（更严格的格式，误判率低）"""
        for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                    # 如果读到 null 字符，说明编码不对，继续尝试
                    if '\x00' not in content:
                        return content
            except (UnicodeDecodeError, UnicodeError):
                continue
        # 兜底：二进制模式读取
        with open(filepath, 'rb') as f:
            raw = f.read()
        return raw.decode('gbk', errors='replace')

    # ──────────────────────────────────────────
    #  读取 / 写入
    # ──────────────────────────────────────────

    def get(self, section: str, key: str, default: str = None) -> Optional[str]:
        """读取指定节下的键值"""
        if section in self._data and key in self._data[section]:
            return self._data[section][key]
        return default

    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """读取整数值"""
        val = self.get(section, key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """读取布尔值 (0/1)"""
        val = self.get(section, key)
        if val is None:
            return default
        return val == '1'

    def set(self, section: str, key: str, value) -> None:
        """设置键值 (内存中，需调用 save() 写回磁盘)"""
        if section not in self._data:
            self._data[section] = OrderedDict()
            self._section_order.append(section)
        self._data[section][key] = str(value)

    def sections(self) -> List[str]:
        """返回所有节名 (保持顺序)"""
        return list(self._section_order)

    def keys(self, section: str) -> List[str]:
        """返回某节下的所有键名"""
        if section in self._data:
            return list(self._data[section].keys())
        return []

    def items(self, section: str) -> List[Tuple[str, str]]:
        """返回某节下的所有键值对"""
        if section in self._data:
            return list(self._data[section].items())
        return []

    def has_section(self, section: str) -> bool:
        """检查节是否存在"""
        return section in self._data

    def has_key(self, section: str, key: str) -> bool:
        """检查键是否存在"""
        return section in self._data and key in self._data[section]

    def remove_section(self, section: str) -> bool:
        """删除整个节，返回是否成功"""
        if section in self._data:
            del self._data[section]
            self._section_order.remove(section)
            return True
        return False

    def remove_key(self, section: str, key: str) -> bool:
        """删除某个键，返回是否成功"""
        if section in self._data and key in self._data[section]:
            del self._data[section][key]
            return True
        return False

    # ──────────────────────────────────────────
    #  序列化 (写入文件)
    # ──────────────────────────────────────────

    def save(self, filepath: str = None) -> None:
        """将当前数据写回 INI 文件"""
        output_path = filepath or self._filepath
        if not output_path:
            raise ValueError("未指定保存路径")

        lines = []
        for section in self._section_order:
            lines.append(f'[{section}]')
            for key, value in self._data[section].items():
                lines.append(f'{key}={value}')
            lines.append('')  # 节之间空一行

        content = '\n'.join(lines)
        # 默认用 GBK 保存 (与雷小伊保持一致)
        with open(output_path, 'w', encoding='gbk') as f:
            f.write(content)

    def dumps(self) -> str:
        """将当前数据序列化为 INI 格式字符串 (用于调试)"""
        lines = []
        for section in self._section_order:
            lines.append(f'[{section}]')
            for key, value in self._data[section].items():
                lines.append(f'{key}={value}')
            lines.append('')
        return '\n'.join(lines)

    def __repr__(self) -> str:
        return f'<IniParser sections={len(self._data)}>'

    def __str__(self) -> str:
        return self.dumps()


# ──────────────────────────────────────────
#  独立运行：快速测试
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        parser = IniParser(sys.argv[1])
        print(f"加载文件: {sys.argv[1]}")
        print(f"共 {len(parser.sections())} 个节\n")
        for sec in parser.sections()[:5]:  # 只显示前5个节
            print(f"[{sec}]")
            for k, v in parser.items(sec):
                print(f"  {k} = {v}")
    else:
        print("用法: python ini_parser.py <文件路径>")
