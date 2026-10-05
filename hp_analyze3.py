# -*- coding: utf-8 -*-
"""HP 条分析 v3: 抓当前对局帧, 找黄色长条(用户确认血条是黄色), 报告矩形与填充率。"""

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


def is_yellow(b, g, r):
    return r > 130 and g > 110 and b < 120 and (r - b) > 60


def find_bars(buf, w, h, y0, y1, pred):
    """在 [y0,y1) 找满足 pred 的像素的水平长条, 按行聚类成矩形。"""
    rows = []
    for yy in range(y0, y1):
        base = yy * w * 4
        run_start = -1
        runs = []
        for xx in range(w):
            i = base + xx * 4
            if pred(buf[i], buf[i + 1], buf[i + 2]):
                if run_start < 0:
                    run_start = xx
            else:
                if run_start >= 0 and xx - run_start > 30:
                    runs.append((run_start, xx))
                run_start = -1
        if run_start >= 0 and w - run_start > 30:
            runs.append((run_start, w))
        for (x0, x1) in runs:
            rows.append((yy, x0, x1))
    clusters = []
    for (yy, x0, x1) in rows:
        merged = False
        for c in clusters:
            if abs(c["y"] - yy) <= 4:
                c["ys"].append(yy)
                c["x0"] = min(c["x0"], x0)
                c["x1"] = max(c["x1"], x1)
                merged = True
                break
        if not merged:
            clusters.append({"y": yy, "ys": [yy], "x0": x0, "x1": x1})
    out = []
    for c in clusters:
        y0c, y1c = min(c["ys"]), max(c["ys"])
        if y1c - y0c >= 3:   # 高度 >= 4px 才像条
            out.append((c["x0"], y0c, c["x1"] - c["x0"], y1c - y0c + 1))
    return out


def fill_ratio(buf, w, h, rect, pred):
    x0, y0, rw, rh = rect
    n_hit = n_tot = 0
    for yy in range(y0, y0 + rh):
        base = yy * w * 4
        for xx in range(x0, x0 + rw):
            i = base + xx * 4
            n_tot += 1
            if pred(buf[i], buf[i + 1], buf[i + 2]):
                n_hit += 1
    return n_hit / max(1, n_tot)


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
    bars = find_bars(frame, w, h, 0, top_h, is_yellow)
    print("[黄色长条候选]")
    for (x0, y0, rw, rh) in bars:
        ratio = fill_ratio(frame, w, h, (x0, y0, rw, rh), is_yellow)
        print("   x=%d..%d y=%d..%d (宽%d 高%d) 黄色占比 %.0f%%"
              % (x0, x0 + rw, y0, y0 + rh, rw, rh, ratio * 100))
    os.makedirs(config.FRAME_DIR, exist_ok=True)
    save_bmp(frame, w, h, os.path.join(config.FRAME_DIR, "hp_v3.bmp"))
    print("[信息] 全帧已存 frames/hp_v3.bmp")


if __name__ == "__main__":
    main()
