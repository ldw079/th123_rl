# -*- coding: utf-8 -*-
"""把顶部区域渲染成 ASCII 色块图: 每 8px 采样一个像素, 按颜色映射字符。"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
import loop
from capture import ScreenCapturer, find_windows, get_client_rect


def classify(b, g, r):
    if r > 130 and g > 110 and b < 120:
        return "Y"   # 黄
    if g > 120 and r < 90 and b < 90:
        return "G"   # 绿
    if b > 150 and g > 130 and r > 150:
        return "W"   # 白/亮
    if b > 120 and g > 100 and r < 100:
        return "C"   # 青/蓝
    if r > 140 and g < 100 and b < 100:
        return "R"   # 红
    if max(b, g, r) < 70:
        return "."   # 暗
    return " "


def main():
    win = None
    for sub in config.TITLE_CANDIDATES:
        ws = find_windows(sub)
        if ws:
            win = ws[0]
            break
    if win is None:
        print("[错误] 找不到游戏窗口")
        sys.exit(1)
    hwnd, title = win
    loop.wait_foreground(hwnd, seconds=5.0)
    x, y, w, h = get_client_rect(hwnd)
    cap = ScreenCapturer(x, y, w, h)
    time.sleep(0.3)
    frame = cap.grab()
    cap.close()

    step = 8
    for yy in range(0, 120, 2):
        row = []
        base = yy * w * 4
        for xx in range(0, w, step):
            i = base + xx * 4
            row.append(classify(frame[i], frame[i + 1], frame[i + 2]))
        print("y=%-3d %s" % (yy, "".join(row)))
    print("x: 0---8---16---24---32---40---48---56---64---72---80---88---96---104--112--120--128(每格8px)")


if __name__ == "__main__":
    main()
