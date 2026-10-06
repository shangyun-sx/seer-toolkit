"""
测试 INI 解析器。

运行: python -m pytest tests/test_ini_parser.py -v
  或: python tests/test_ini_parser.py
"""

import os
import sys
import tempfile

# Windows GBK 终端下强制 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.ini_parser import IniParser


def test_basic_parse():
    """测试基本解析功能"""
    content = (
        "[Section1]\n"
        "key1=value1\n"
        "key2=value2\n"
        "\n"
        "[Section2]\n"
        "name=测试\n"
        "enable=1\n"
    )
    # 写入临时文件 (用 GBK 编码，与雷小伊一致)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.ini', delete=False) as f:
        f.write(content.encode('gbk'))
        tmpfile = f.name

    try:
        parser = IniParser(tmpfile)
        assert parser.get('Section1', 'key1') == 'value1'
        assert parser.get('Section1', 'key2') == 'value2'
        assert parser.get('Section2', 'name') == '测试'
        assert parser.get_int('Section2', 'enable') == 1
        assert parser.get_bool('Section2', 'enable') is True
        assert parser.get('NoExist', 'key', 'default') == 'default'
    finally:
        os.unlink(tmpfile)


def test_sections_order():
    """测试节顺序保持"""
    parser = IniParser()
    parser.set('B', 'k', 'v')
    parser.set('A', 'k', 'v')
    parser.set('C', 'k', 'v')
    assert parser.sections() == ['B', 'A', 'C']


def test_set_and_save():
    """测试修改并保存"""
    parser = IniParser()
    parser.set('Settings', 'volume', '80')
    parser.set('Settings', 'mute', '0')
    parser.set('Display', 'width', '1920')

    # 保存到临时文件 (二进制模式避免编码问题)
    fd, tmpfile = tempfile.mkstemp(suffix='.ini')
    os.close(fd)

    try:
        parser.save(tmpfile)

        # 重新加载验证
        parser2 = IniParser(tmpfile)
        assert parser2.get('Settings', 'volume') == '80'
        assert parser2.get_bool('Settings', 'mute') is False
        assert parser2.get('Display', 'width') == '1920'
    finally:
        os.unlink(tmpfile)


def test_empty_file():
    """测试空文件"""
    parser = IniParser()
    assert parser.sections() == []
    assert parser.get('A', 'b') is None


def test_remove():
    """测试删除功能"""
    parser = IniParser()
    parser.set('S', 'k1', 'v1')
    parser.set('S', 'k2', 'v2')

    assert parser.remove_key('S', 'k1') is True
    assert parser.has_key('S', 'k1') is False
    assert parser.has_key('S', 'k2') is True

    assert parser.remove_section('S') is True
    assert parser.has_section('S') is False


def test_dumps():
    """测试序列化输出"""
    parser = IniParser()
    parser.set('Config', 'speed', '3')
    output = parser.dumps()
    assert '[Config]' in output
    assert 'speed=3' in output


# ──────────────────────────────────────────
#  save() 必须保住文件原貌（行级补丁）
#
#  背景: 旧版 save() 是「从内存数据整份重新序列化」，注释和空行全丢。
#  而 AccountManager.toggle_task() 会把它写回**游戏自己的**
#  Config/<QQ>.ini —— 用户点一下开关，游戏配置里的注释就没了。
# ──────────────────────────────────────────

def _save_roundtrip(content, mutate, encoding='gbk'):
    """把 content 落到临时文件，加载 -> mutate -> save()，返回读回的文本"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'test.ini')
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)

        parser = IniParser(path)
        mutate(parser)
        parser.save()

        with open(path, encoding=encoding) as f:
            return f.read()


def test_save_preserves_comments_and_blank_lines():
    """save() 不能把注释和空行抹掉"""
    content = ('[任务_1]\n'
               '; 这是注释，必须保留\n'
               '开关=0\n'
               '\n'
               '; 段落说明\n'
               '参数=abc\n')

    result = _save_roundtrip(content, lambda p: p.set('任务_1', '开关', '1'))

    assert '; 这是注释，必须保留' in result, result
    assert '; 段落说明' in result, result
    assert '开关=1' in result, result
    assert '参数=abc' in result, result
    assert '\n\n' in result, f'空行丢了: {result!r}'


def test_save_rewrites_only_changed_line():
    """值没变的行原样保留，不制造无谓 diff"""
    content = '[S]\nkey = value\nother=untouched\n'

    result = _save_roundtrip(content, lambda p: p.set('S', 'other', 'changed'))

    assert 'key = value' in result, f'未改动的行被重写了: {result!r}'
    assert 'other=changed' in result, result


def test_save_puts_new_key_inside_its_own_section():
    """新增的键落在它**所属那节**的末尾，不能跑到文件末尾去"""
    content = '[A]\nk1=v1\n\n[B]\nk2=v2\n'

    result = _save_roundtrip(content, lambda p: p.set('A', 'k3', 'v3'))

    assert 'k3=v3' in result, result
    assert result.index('k3=v3') < result.index('[B]'), \
        f'新键跑到后面的节去了: {result!r}'
    assert result.index('k3=v3') > result.index('k1=v1'), result


def test_save_drops_removed_key_and_section():
    """remove_key / remove_section 之后，对应的行和整块都不该还在"""
    content = '[A]\nk1=v1\nk2=v2\n\n[B]\nk3=v3\n'

    def mutate(p):
        p.remove_key('A', 'k2')
        p.remove_section('B')

    result = _save_roundtrip(content, mutate)

    assert 'k2' not in result, result
    assert '[B]' not in result, result
    assert 'k1=v1' in result, result


def test_save_appends_brand_new_section():
    """凭空 set 出来的新节追加到文件末尾"""
    content = '[A]\nk1=v1\n'

    result = _save_roundtrip(content, lambda p: p.set('New', 'k', 'v'))

    assert '[New]' in result, result
    assert result.index('[New]') > result.index('[A]'), result
    assert 'k=v' in result, result


def test_save_survives_non_gbk_chars():
    """GBK 文件里写入 GBK 表示不了的字符(emoji): 降级成 '?', 不抛异常。

    旧版这里直接 UnicodeEncodeError —— 用户点一下开关就崩。
    """
    content = '[S]\n名字=测试\n'      # 含中文 -> 按 GBK 探测，save 也走 GBK

    result = _save_roundtrip(content, lambda p: p.set('S', 'nick', '小明🎉'))

    assert '小明' in result, result          # 中文部分照常写入
    assert '🎉' not in result, result        # emoji 降级了 —— 但没崩


def test_save_ascii_file_defaults_to_gbk():
    """纯 ASCII 文件按 GBK 写回。

    雷小伊按 GBK 读；若这里写 UTF-8，用户 set 进去的中文会被游戏读成乱码。
    旧版永远写 GBK，这条规则就是为了不把那个行为弄丢。
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'test.ini')
        with open(path, 'w', encoding='ascii') as f:
            f.write('[S]\nname=abc\n')

        parser = IniParser(path)
        parser.set('S', 'nick', '小明')
        parser.save()

        with open(path, 'rb') as f:
            raw = f.read()

    gbk_bytes = '小明'.encode('gbk')    # D0 A1 C3 F7
    utf8_bytes = '小明'.encode()        # E5 B0 8F E6 98 8E（encode() 默认就是 utf-8）

    assert gbk_bytes in raw, raw
    assert utf8_bytes not in raw, raw


def test_save_keeps_utf8_file_as_utf8():
    """UTF-8 的文件存回去还是 UTF-8，不会被悄悄改成 GBK"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'test.ini')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('[S]\nname=测试\n')

        parser = IniParser(path)
        parser.set('S', 'name', '测试2')
        parser.save()

        # 严格按 UTF-8 读得出来 = 没被写成 GBK（GBK 的中文按 UTF-8 解会报错）
        with open(path, encoding='utf-8') as f:
            result = f.read()

    assert 'name=测试2' in result, result


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_basic_parse,
        test_sections_order,
        test_set_and_save,
        test_empty_file,
        test_remove,
        test_dumps,
        test_save_preserves_comments_and_blank_lines,
        test_save_rewrites_only_changed_line,
        test_save_puts_new_key_inside_its_own_section,
        test_save_drops_removed_key_and_section,
        test_save_appends_brand_new_section,
        test_save_survives_non_gbk_chars,
        test_save_ascii_file_defaults_to_gbk,
        test_save_keeps_utf8_file_as_utf8,
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
            print(f"  💥 {test.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
