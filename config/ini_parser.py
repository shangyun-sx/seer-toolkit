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
import logging
from collections import OrderedDict
from typing import Optional, List, Tuple, Dict, Set

log = logging.getLogger(__name__)

#: 节头 `[Name]` 与键值对 `key=value` 的行格式。
#: load() 和行级补丁 (_patch_lines) 共用同一套，避免两处写法漂移。
_SECTION_RE = re.compile(r'^\[(.+)\]$')
_KV_RE = re.compile(r'^([^=]+)=(.*)$')


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
        # 原始行。save() 靠它做行级补丁，从而保留注释 / 空行 / 原始顺序
        self._raw_lines: Optional[List[str]] = None
        # 加载时探测到的编码。save() 沿用它，避免把 UTF-8 文件写成 GBK
        self._encoding: Optional[str] = None

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
        self._encoding = None

        # 尝试多种编码
        content = self._read_with_encoding(filepath)
        # 保留未加工的行 —— save() 靠它做行级补丁
        self._raw_lines = content.splitlines()

        current_section = None
        for line in content.splitlines():
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith(';') or line.startswith('#'):
                continue

            # 匹配节: [SectionName]
            section_match = _SECTION_RE.match(line)
            if section_match:
                current_section = section_match.group(1).strip()
                if current_section not in self._data:
                    self._data[current_section] = OrderedDict()
                    self._section_order.append(current_section)
                continue

            # 匹配键值对: key=value
            kv_match = _KV_RE.match(line)
            if kv_match and current_section is not None:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                self._data[current_section][key] = value

    def _read_with_encoding(self, filepath: str) -> str:
        """尝试用多种编码读取文件，优先 UTF-8（更严格的格式，误判率低）。

        命中的编码记到 `self._encoding`，save() 会沿用它 —— 这样 UTF-8 的
        文件存回去还是 UTF-8，不会在读写之间被悄悄改成 GBK。
        """
        for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                    # 如果读到 null 字符，说明编码不对，继续尝试
                    if '\x00' not in content:
                        # 纯 ASCII 在 UTF-8 和 GBK 下字节完全相同，读进来都对。
                        # 但**写回**时不一样：雷小伊按 GBK 读，所以这里刻意
                        # 记成 GBK，免得用户之后 set() 一个中文昵称被写成
                        # UTF-8，游戏读出来是乱码。
                        self._encoding = ('gbk' if content.isascii() else encoding)
                        return content
            except (UnicodeDecodeError, UnicodeError):
                continue
        # 兜底：二进制模式读取
        with open(filepath, 'rb') as f:
            raw = f.read()
        self._encoding = 'gbk'
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
        """将当前数据写回 INI 文件。

        从磁盘加载过的 parser 走**行级补丁**：只重写值有变化的行，
        注释 / 空行 / 键的原始顺序都会保留（见 `_patch_lines`）。
        只有凭空新建的 parser（没有原始文本可参照）才退回整份重新生成。

        编码沿用加载时探测到的那个；探测不到就按 GBK（与雷小伊一致）。
        目标编码写不了的字符（如 GBK 写不了的 emoji）降级成 'replace'，
        而不是抛 UnicodeEncodeError —— 宁可字符变成 '?'，也不要让用户
        点一下开关就崩，把配置文件留在半写状态。
        """
        output_path = filepath or self._filepath
        if not output_path:
            raise ValueError("未指定保存路径")

        encoding = self._encoding or 'gbk'
        text = self._serialize()

        # errors='replace' 会把编码写不出的字符悄悄换成 '?' —— 那是数据损坏，
        # 只是不抛异常而已。至少留下痕迹：真的发生了就报一声。
        try:
            text.encode(encoding)
        except UnicodeEncodeError as e:
            log.warning('%s 里有 %s 写不出的字符，写回时会被替换成 "?": %s',
                        output_path, encoding, e)

        with open(output_path, 'w', encoding=encoding, errors='replace') as f:
            f.write(text)

    def _serialize(self) -> str:
        """有原始行就打补丁，否则整份重新生成"""
        if self._raw_lines is None:
            return self.dumps()
        return self._patch_lines()

    def _patch_lines(self) -> str:
        """在原始行上打补丁：只动值变了的行，其余原样吐回去。

        规则:
          * 值没变 -> 原样保留（连 `key = value` 里的空格都不动，不制造无谓 diff）
          * 值变了 -> 只重写这一行
          * remove_key / remove_section 掉的 -> 整行 / 整块丢弃
          * set() 新增的键 -> 补在**它所属那节的末尾**，不是文件末尾
          * 全新的节 -> 追加到文件末尾
        """
        data = self._data
        raw = self._raw_lines or []

        # 先记下原始文件里出现过哪些节，最后靠它判断"哪些节是全新的"。
        # 写成显式循环而不是集合推导：推导里 if 和元素各调一次 match()，
        # 静态检查没法把两者关联起来（会认为 group() 可能作用在 None 上）。
        seen_sections: Set[str] = set()
        for raw_line in raw:
            match = _SECTION_RE.match(raw_line.strip())
            if match:
                seen_sections.add(match.group(1).strip())

        out: List[str] = []
        written: Set[Tuple[str, str]] = set()
        current: Optional[str] = None
        keeping = True        # 当前节是否还在 data 里（被 remove_section 的就不在）

        for line in raw:
            stripped = line.strip()

            section_match = _SECTION_RE.match(stripped)
            if section_match:
                # 离开本节前，把这一节里新增的键补在它末尾
                if keeping:
                    self._append_new_keys(out, current, written)
                current = section_match.group(1).strip()
                keeping = current in data
                if keeping:
                    out.append(line)
                continue

            if not keeping:
                continue      # 被删掉的节，整块不要

            kv_match = _KV_RE.match(stripped)
            if kv_match and current is not None:
                key = kv_match.group(1).strip()
                entries = data[current]      # 别叫 section —— 下面那个循环变量才叫 section
                if key not in entries:
                    continue  # 这个键被 remove_key 了
                written.add((current, key))
                if entries[key] == kv_match.group(2).strip():
                    out.append(line)                # 值没变，原样保留
                else:
                    out.append(f'{key}={entries[key]}')
                continue

            out.append(line)  # 注释 / 空行 / 认不出的行 -> 原样保留

        if keeping:
            self._append_new_keys(out, current, written)

        # 全新的节，追加到文件末尾
        for section in self._section_order:
            if section in seen_sections:
                continue
            if out and out[-1].strip():
                out.append('')
            out.append(f'[{section}]')
            for key, value in data[section].items():
                out.append(f'{key}={value}')

        return '\n'.join(out)

    def _append_new_keys(self, out: List[str], section: Optional[str],
                         written: Set[Tuple[str, str]]) -> None:
        """把 `section` 里还没写出去的键追加到 out 末尾。

        插在节末尾**空行之前** —— 否则新键会紧贴在下一个节头上面，
        看起来像属于下一节。
        """
        if section is None or section not in self._data:
            return

        pending = [(key, value) for key, value in self._data[section].items()
                   if (section, key) not in written]
        if not pending:
            return

        # 先把尾部空行摘下来，插完再放回去
        trailing: List[str] = []
        while out and not out[-1].strip():
            trailing.append(out.pop())

        for key, value in pending:
            out.append(f'{key}={value}')
            written.add((section, key))

        out.extend(reversed(trailing))

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
