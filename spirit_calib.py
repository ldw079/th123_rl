# -*- coding: utf-8 -*-
"""灵力珠标定: 在底部区域找蓝色菱形簇, 输出每颗珠子的精确区域。"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

import config
import loop
from capture import ScreenCapturer, find_windows, get_client_rect


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
    cap = ScreenCapturer(x, y, w, h, scale=config.CAPTURE_SCALE)
    time.sleep(0.3)
    frame = cap.grab()
    cw, ch = cap.w, cap.h
    cap.close()

    img = np.frombuffer(frame, dtype=np.uint8).reshape(ch, cw, 4)
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    blue = (b > 120) & (b - r > 40) & (b - g > 20)

    # 底部带 (y 0.90-1.0)
    y0, y1 = int(ch * 0.90), ch
    band = blue[y0:y1]
    colsum = band.sum(axis=0)
    print("[蓝色像素按列分布] (只列连续>5的段)")
    runs = []
    start = None
    for xx in range(cw):
        if colsum[xx] > 3:
            if start is None:
                start = xx
        else:
            if start is not None and xx - start >= 5:
                ys = np.where(band[:, start:xx].any(axis=1))[0]
                runs.append((start, xx, y0 + ys.min(), y0 + ys.max(),
                             int(band[:, start:xx].sum())))
            start = None
    if start is not None and cw - start >= 5:
        ys = np.where(band[:, start:].any(axis=1))[0]
        runs.append((start, cw, y0 + ys.min(), y0 + ys.max(),
                     int(band[:, start:].sum())))
    for (x0, x1, ry0, ry1, n) in runs:
        print("  x=%d..%d y=%d..%d 蓝px=%d  (比例 x=%.3f-%.3f y=%.3f-%.3f)"
              % (x0, x1, ry0, ry1, n, x0 / cw, x1 / cw, ry0 / ch, ry1 / ch))


if __name__ == "__main__":
    main()
