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


if __name__ == '__main__':
    # 不使用 pytest 也能跑
    tests = [
        test_basic_parse,
        test_sections_order,
        test_set_and_save,
        test_empty_file,
        test_remove,
        test_dumps,
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
