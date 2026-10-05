# -*- coding: utf-8 -*-
"""dxcam(DXGI) 抓屏基准: 对比 GDI, 验证 60fps 可行性。"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

import dxcam

from capture import get_client_rect, find_windows, user32
import config


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
    hwnd = win[0]
    x, y, w, h = get_client_rect(hwnd)
    print("[信息] 游戏客户区 (%d,%d) %dx%d" % (x, y, w, h))

    cam = dxcam.create(output_color="BGR")
    if cam is None:
        print("[错误] dxcam 初始化失败(不支持 DXGI?)")
        sys.exit(1)

    # 预热
    for _ in range(5):
        f = cam.grab(region=(x, y, x + w, y + h))
    times = []
    N = 120
    for _ in range(N):
        s = time.perf_counter()
        f = cam.grab(region=(x, y, x + w, y + h))
        if f is not None:
            arr = np.asarray(f)[::2, ::2]      # 2x 降采样
        times.append((time.perf_counter() - s) * 1000)
    valid = [t for t, f in zip(times, [1] * N) if t > 0]
    avg = sum(valid) / len(valid)
    print("[结果] dxcam 区域抓取+降采样: 平均 %.2f ms/帧, 最大 %.2f ms"
          % (avg, max(valid)))
    budget = 1000.0 / config.FPS
    print("[判定] %s (预算 %.2f ms/帧 @ %.1ffps)"
          % ("60fps 可行" if avg < budget * 0.6 else "偏慢", budget, config.FPS))
    cam.release()


if __name__ == "__main__":
    main()
