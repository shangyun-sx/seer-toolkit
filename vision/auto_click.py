"""
自动点击模块 —— 截屏 → 匹配模板 → 模拟点击。

整合 pyautogui 和 template_match，实现完整的"看到按钮就点"流程。

⚠️ 使用前请安装依赖:
    pip install pyautogui opencv-python numpy

⚠️ 自动操作鼠标有一定风险，请在理解代码的前提下使用。
"""

import time
from typing import Optional, Tuple

# 图像匹配使用 OpenCV
import cv2
import numpy as np

# 桌面操作用 pyautogui
# (如果未安装，import 时会报错，不影响仅使用匹配功能)
try:
    import pyautogui
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

from .template_match import find_with_multi_templates, load_screenshot_from_pil


class AutoClicker:
    """自动点击器 —— 检测并点击屏幕上的目标按钮"""

    def __init__(self, template_dir: str, threshold: float = 0.85):
        """
        template_dir: 模板图片目录
        threshold: 匹配置信度阈值
        """
        self.template_dir = template_dir
        self.threshold = threshold
        self.last_click: Optional[Tuple[int, int]] = None
        self.click_count = 0

        if not _HAS_PYAUTOGUI:
            raise ImportError(
                "需要安装 pyautogui 才能使用自动点击功能。\n"
                "运行: pip install pyautogui"
            )

    def capture_screen(self) -> np.ndarray:
        """截取当前屏幕，返回 OpenCV BGR 格式"""
        pil_img = pyautogui.screenshot()
        return load_screenshot_from_pil(pil_img)

    def detect(self) -> Tuple[Optional[Tuple[int, int]], float, Optional[str]]:
        """
        检测屏幕上是否有目标按钮。

        返回: (坐标, 相似度, 模板名)
        """
        screen = self.capture_screen()
        return find_with_multi_templates(screen, self.template_dir,
                                         threshold=self.threshold)

    def click_at(self, x: int, y: int) -> None:
        """在指定坐标点击"""
        pyautogui.click(x, y)
        self.last_click = (x, y)
        self.click_count += 1

    def detect_and_click(self) -> bool:
        """
        检测目标并点击。如果找到了就点，找不到就跳过。

        返回: 是否执行了点击
        """
        location, score, tpl_name = self.detect()
        if location is None:
            return False

        x, y = location
        self.click_at(x, y)
        print(f"  🖱️ 点击 ({x}, {y}) — 匹配: {tpl_name} ({score:.1%})")
        return True

    def watch_loop(self, interval: float = 2.0, max_clicks: int = 0):
        """
        持续监控屏幕，发现目标就点击。

        interval: 检测间隔 (秒)
        max_clicks: 最大点击次数 (0 表示无限)
        """
        print(f"🔍 开始监控... (间隔 {interval}s, 阈值 {self.threshold:.0%})")
        print(f"   模板目录: {self.template_dir}")
        print(f"   按 Ctrl+C 停止\n")

        try:
            while True:
                clicked = self.detect_and_click()
                if not clicked:
                    print(f"  · 未检测到目标")
                else:
                    if max_clicks > 0 and self.click_count >= max_clicks:
                        print(f"\n✅ 已完成 {max_clicks} 次点击，停止")
                        break
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n⏹️ 监控停止 (共点击 {self.click_count} 次)")


# ──────────────────────────────────────────
#  独立运行
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys
    template_dir = sys.argv[1] if len(sys.argv) > 1 else '识图/img'

    clicker = AutoClicker(template_dir, threshold=0.85)
    clicker.watch_loop(interval=2.0)
