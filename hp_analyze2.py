# -*- coding: utf-8 -*-
"""HP 条分析 v2: 按"颜色均匀的长横条"找 HUD 条(不限亮度), 并打印顶部逐行摘要。"""

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
from perception import save_bmp


def row_profile(buf, w, yy):
    """一行内均匀色段(方差小, 长度>=60): [(x0,x1,平均BGR)]"""
    base = yy * w * 4
    segs = []
    s0 = 0
    prev = None
    for xx in range(w):
        i = base + xx * 4
        c = (buf[i], buf[i + 1], buf[i + 2])
        if prev is None:
            prev = c
            s0 = 0
            continue
        dist = abs(c[0] - prev[0]) + abs(c[1] - prev[1]) + abs(c[2] - prev[2])
        if dist > 60:   # 颜色跳变 = 段边界
            if xx - s0 >= 60:
                seg = buf[base + s0 * 4: base + xx * 4]
                n = (xx - s0)
                mb = sum(seg[0::4]) // n
                mg = sum(seg[1::4]) // n
                mr = sum(seg[2::4]) // n
                segs.append((s0, xx, (mb, mg, mr)))
            s0 = xx
        prev = c
    if w - s0 >= 60:
        seg = buf[base + s0 * 4:]
        n = (w - s0)
        mb = sum(seg[0::4]) // n
        mg = sum(seg[1::4]) // n
        mr = sum(seg[2::4]) // n
        segs.append((s0, w, (mb, mg, mr)))
    return segs


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
    print("[窗口]", title)
    loop.wait_foreground(hwnd, seconds=5.0)

    x, y, w, h = get_client_rect(hwnd)
    cap = ScreenCapturer(x, y, w, h)
    time.sleep(0.3)
    frame = cap.grab()
    cap.close()

    top_h = int(h * 0.13)
    print("[顶部逐行分段]  (BGR 平均色)")
    for yy in range(0, top_h, 4):
        segs = row_profile(frame, w, yy)
        if segs:
            desc = " | ".join("x%d-%d(%d,%d,%d)" % (a, b, c[0], c[1], c[2]) for a, b, c in segs)
            print("  y=%-3d: %s" % (yy, desc))
    os.makedirs(config.FRAME_DIR, exist_ok=True)
    save_bmp(frame, w, h, os.path.join(config.FRAME_DIR, "top_region.bmp"))


if __name__ == "__main__":
    main()
