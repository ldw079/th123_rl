# -*- coding: utf-8 -*-
"""HUD 标定: 抓一帧, 把顶部血条以下区域和底部区域渲染成 ASCII 色块图,
定位灵力珠(蓝色菱形)和卡牌显示区。"""

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
        return "Y"   # 黄(HP)
    if b > 130 and g > 90 and r < 110:
        return "B"   # 蓝(灵力珠?)
    if b > 150 and g > 140 and r > 150:
        return "W"   # 白/亮
    if g > 120 and r < 100 and b < 100:
        return "G"   # 绿
    if r > 140 and g < 100 and b < 100:
        return "R"   # 红
    if max(b, g, r) < 70:
        return "."
    return " "


def dump(frame, w, h, y0, y1, label, step=8, xstep=6):
    print("==== %s (y=%d..%d) ====" % (label, y0, y1))
    for yy in range(y0, y1, 2):
        row = []
        base = yy * w * 4
        for xx in range(0, w, xstep):
            i = base + xx * 4
            row.append(classify(frame[i], frame[i + 1], frame[i + 2]))
        print("y=%-4d %s" % (yy, "".join(row)))
    print("x: 每格 %d px" % xstep)


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
    print("[信息] 缩放后尺寸 %dx%d" % (cw, ch))
    # 顶部 HUD 全区(血条+下方)
    dump(frame, cw, ch, 0, int(ch * 0.22), "顶部HUD")
    # 底部(卡牌手牌区?)
    dump(frame, cw, ch, int(ch * 0.80), ch - 2, "底部")


if __name__ == "__main__":
    main()
