"""
图像模板匹配模块。

在屏幕截图中搜索预定义的模板图像 (如"确认"按钮)，
返回匹配位置和相似度。

核心算法: OpenCV matchTemplate + TM_CCOEFF_NORMED

雷小伊的 识图/img/ 目录下有 18 张不同大小的"确认"按钮模板，
需要在搜索时全部尝试，取最佳匹配结果。
"""

import cv2
import numpy as np
import os
import glob
from typing import Optional, Tuple, List


def find_template(
    screenshot: np.ndarray,
    template_path: str,
    threshold: float = 0.8
) -> Tuple[Optional[Tuple[int, int]], float]:
    """
    在截图中搜索单个模板。

    参数:
        screenshot: BGR 格式的截图 (numpy 数组)
        template_path: 模板图片路径
        threshold: 相似度阈值 (0.0 ~ 1.0)

    返回:
        (中心坐标, 相似度) — 找不到时坐标为 None
    """
    template = cv2.imread(template_path)
    if template is None:
        raise FileNotFoundError(f"无法读取模板: {template_path}")

    h, w = template.shape[:2]

    # 模板匹配：在截图上滑动模板，计算归一化相关系数
    result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < threshold:
        return None, max_val

    center_x = max_loc[0] + w // 2
    center_y = max_loc[1] + h // 2
    return (center_x, center_y), max_val


def find_with_multi_templates(
    screenshot: np.ndarray,
    template_dir: str,
    pattern: str = '确认*.bmp',
    threshold: float = 0.8
) -> Tuple[Optional[Tuple[int, int]], float, Optional[str]]:
    """
    在截图中搜索多个模板，返回最佳匹配。

    参数:
        screenshot: BGR 格式的截图
        template_dir: 模板图片所在目录
        pattern: 模板文件匹配模式
        threshold: 相似度阈值

    返回:
        (中心坐标, 最高相似度, 匹配的模板文件名)
    """
    best_score = 0.0
    best_location: Optional[Tuple[int, int]] = None
    best_template: Optional[str] = None

    search_pattern = os.path.join(template_dir, pattern)
    template_files = glob.glob(search_pattern)

    if not template_files:
        raise FileNotFoundError(f"在 {template_dir} 中未找到匹配 '{pattern}' 的模板")

    for tpl_path in template_files:
        location, score = find_template(screenshot, tpl_path, threshold=0.0)
        if score > best_score:
            best_score = score
            best_location = location
            best_template = os.path.basename(tpl_path)

    # 低于阈值视为未找到
    if best_score < threshold:
        return None, best_score, best_template

    return best_location, best_score, best_template


def draw_result(
    screenshot: np.ndarray,
    location: Tuple[int, int],
    template_path: str,
    score: float
) -> np.ndarray:
    """
    在截图上绘制匹配结果 (用于调试可视化)。

    返回绘制后的图像副本。
    """
    output = screenshot.copy()
    template = cv2.imread(template_path)
    if template is None:
        return output

    h, w = template.shape[:2]
    x = location[0] - w // 2
    y = location[1] - h // 2

    # 画绿色矩形框
    cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 0), 2)
    # 标注相似度
    label = f'{score:.1%}'
    cv2.putText(output, label, (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    return output


def load_screenshot_from_file(filepath: str) -> np.ndarray:
    """从文件加载截图"""
    img = cv2.imread(filepath)
    if img is None:
        raise FileNotFoundError(f"无法读取截图: {filepath}")
    return img


def load_screenshot_from_pil(pil_image) -> np.ndarray:
    """
    将 PIL/Pillow Image 转换为 OpenCV 格式 (BGR)。

    用于配合 pyautogui/pyscreenshot 使用:
        import pyautogui
        screenshot = pyautogui.screenshot()
        cv_img = load_screenshot_from_pil(screenshot)
    """
    rgb = np.array(pil_image)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr


# ──────────────────────────────────────────
#  独立运行：测试模板匹配
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("用法: python template_match.py <截图路径> <模板目录>")
        print("示例: python template_match.py screenshot.png 识图/img")
        sys.exit(1)

    screenshot_path = sys.argv[1]
    template_dir = sys.argv[2]

    print(f"加载截图: {screenshot_path}")
    screen = load_screenshot_from_file(screenshot_path)
    print(f"截图尺寸: {screen.shape[1]}x{screen.shape[0]}")

    location, score, tpl_name = find_with_multi_templates(screen, template_dir)

    if location:
        print(f"✅ 找到匹配!")
        print(f"   模板: {tpl_name}")
        print(f"   位置: {location}")
        print(f"   相似度: {score:.2%}")

        # 保存标记结果
        result = draw_result(screen, location,
                             os.path.join(template_dir, tpl_name), score)
        output_path = 'match_result.png'
        cv2.imwrite(output_path, result)
        print(f"   结果已保存: {output_path}")
    else:
        print(f"❌ 未找到匹配 (最高相似度: {score:.2%}, 模板: {tpl_name})")
