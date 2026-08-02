"""
测试图像模板匹配。

运行:
    python tests/test_template_match.py <截图路径> <模板目录>
"""

import os
import sys
import numpy as np

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vision.template_match import (
    find_template,
    find_with_multi_templates,
    load_screenshot_from_file,
)


def test_find_with_synthetic_image():
    """用合成图像测试匹配功能"""
    import cv2

    print("  生成测试图像...")

    # 创建一个 500x500 的灰色背景
    screen = np.full((500, 500, 3), fill_value=128, dtype=np.uint8)

    # 画一个明显的"按钮" —— 白色矩形 + 黑色文字
    cv2.rectangle(screen, (100, 100), (200, 150), (255, 255, 255), -1)
    cv2.putText(screen, 'OK', (115, 135),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

    # 保存为临时模板
    template = screen[100:150, 100:200]  # 裁剪出按钮区域

    tmpdir = 'temp_test_templates'
    os.makedirs(tmpdir, exist_ok=True)
    tpl_path = os.path.join(tmpdir, 'test_button.bmp')
    cv2.imwrite(tpl_path, template)

    try:
        # 搜索模板
        location, score = find_template(screen, tpl_path, threshold=0.9)
        print(f"  匹配位置: {location}, 相似度: {score:.2%}")
        assert location is not None, "应该能找到模板"
        # 应该匹配到按钮中心 (150, 125)
        assert abs(location[0] - 150) <= 1
        assert abs(location[1] - 125) <= 1
        print("  ✅ 合成图像匹配成功")
    finally:
        os.unlink(tpl_path)
        os.rmdir(tmpdir)


def test_template_not_found():
    """测试找不到的情况"""
    import cv2

    # 全黑图像 vs 全白模板 — 不可能匹配
    screen = np.zeros((200, 200, 3), dtype=np.uint8)
    white = np.full((50, 50, 3), fill_value=255, dtype=np.uint8)

    tmpdir = 'temp_test_templates'
    os.makedirs(tmpdir, exist_ok=True)
    tpl_path = os.path.join(tmpdir, 'white.bmp')
    cv2.imwrite(tpl_path, white)

    try:
        location, score = find_template(screen, tpl_path, threshold=0.9)
        assert location is None
        print(f"  ✅ 正确返回 None (相似度: {score:.2%})")
    finally:
        os.unlink(tpl_path)
        os.rmdir(tmpdir)


if __name__ == '__main__':
    print("图像匹配单元测试:")
    test_find_with_synthetic_image()
    test_template_not_found()
    print("\n✅ 所有图像匹配测试通过")
