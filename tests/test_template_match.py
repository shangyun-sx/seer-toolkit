"""
测试图像模板匹配（用合成图像，不需要真实截图）。

运行: python -m pytest tests/test_template_match.py -v
  或: python tests/test_template_match.py
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
    """测试找不到的情况。

    注意：这里**不能**用「全白模板 vs 全黑屏幕」来造「找不到」。
    TM_CCOEFF_NORMED 是**归一化**互相关，公式里会除以模板的标准差；
    纯色模板的标准差是 0，分母为 0，OpenCV 会直接给出 1.0 —— 结果变成
    「处处都匹配」，和直觉正好相反。（旧版 OpenCV 返回 NaN，NaN > 阈值
    恒为假，所以这个用例以前是「碰巧」过的。）

    所以要用一个**有结构**的模板：标准差非 0，和纯黑屏幕的相关系数才是真的 0。
    """
    import cv2

    screen = np.zeros((200, 200, 3), dtype=np.uint8)
    # 固定种子，保证可复现
    noise = np.random.default_rng(0).integers(0, 255, (50, 50, 3), dtype=np.uint8)

    tmpdir = 'temp_test_templates'
    os.makedirs(tmpdir, exist_ok=True)
    tpl_path = os.path.join(tmpdir, 'noise.bmp')
    cv2.imwrite(tpl_path, noise)

    try:
        location, score = find_template(screen, tpl_path, threshold=0.9)
        assert location is None, f"不该匹配到，实际位置 {location}、分数 {score}"
        print(f"  ✅ 正确返回 None (相似度: {score:.2%})")
    finally:
        os.unlink(tpl_path)
        os.rmdir(tmpdir)


if __name__ == '__main__':
    print("图像匹配单元测试:")
    test_find_with_synthetic_image()
    test_template_not_found()
    print("\n✅ 所有图像匹配测试通过")
