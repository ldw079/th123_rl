# -*- coding: utf-8 -*-
"""HP 条自动标定: 抓一帧对局画面, 分析顶部区域, 找出 HP 条的位置与颜色。

输出: 顶部区域中"高亮度/高饱和"的水平长条候选(HP 条通常就是这种长条),
并保存顶部裁剪图 frames/top_region.bmp 供人工核对。
"""

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


def analyze(buf, w, h, y0, y1):
    """在 [y0,y1) 行内找高亮长条。返回 (行, x范围, 亮像素数, 平均颜色)。"""
    rows = []
    for yy in range(y0, y1):
        base = yy * w * 4
        runs = []
        run_start = -1
        for xx in range(w):
            i = base + xx * 4
            b, g, r = buf[i], buf[i + 1], buf[i + 2]
            mx, mn = max(r, g, b), min(r, g, b)
            bright = mx > 120 and (mx - mn) > 40   # 亮且饱和
            if bright:
                if run_start < 0:
                    run_start = xx
            else:
                if run_start >= 0 and xx - run_start > 60:
                    runs.append((run_start, xx))
                run_start = -1
        if run_start >= 0 and w - run_start > 60:
            runs.append((run_start, w))
        for (x0, x1) in runs:
            rows.append((yy, x0, x1))
    # 合并相邻行
    return rows


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
    print("[信息] 客户区 %dx%d" % (w, h))

    top_h = int(h * 0.14)   # 顶部 14% 区域(2x 缩放下足够盖住 HP 条)
    os.makedirs(config.FRAME_DIR, exist_ok=True)
    # 保存顶部裁剪图(行序自上而下, BGRA)
    save_bmp(frame, w, h, os.path.join(config.FRAME_DIR, "top_region.bmp"))

    rows = analyze(frame, w, h, 0, top_h)
    # 按 y 分组聚类
    clusters = []
    for (yy, x0, x1) in rows:
        merged = False
        for c in clusters:
            if abs(c["y"] - yy) <= 3:
                c["rows"].append(yy)
                c["x0"] = min(c["x0"], x0)
                c["x1"] = max(c["x1"], x1)
                merged = True
                break
        if not merged:
            clusters.append({"y": yy, "rows": [yy], "x0": x0, "x1": x1})
    print("[候选长条]")
    for c in sorted(clusters, key=lambda c: c["y"]):
        y0c, y1c = min(c["rows"]), max(c["rows"])
        print("   y=%d..%d  x=%d..%d  (宽 %d, 高 %d)"
              % (y0c, y1c, c["x0"], c["x1"], c["x1"] - c["x0"], y1c - y0c + 1))
        # 取中心行颜色
        yy = (y0c + y1c) // 2
        base = yy * w * 4
        i = base + ((c["x0"] + c["x1"]) // 2) * 4
        print("    中心颜色 BGR=(%d,%d,%d)" % (frame[i], frame[i + 1], frame[i + 2]))


if __name__ == "__main__":
    main()
