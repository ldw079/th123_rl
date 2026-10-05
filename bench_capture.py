# -*- coding: utf-8 -*-
"""抓屏基准测试: 模拟游戏窗口尺寸(640x480)的抓帧耗时, 确认 60fps 预算是否够。

运行: <python> bench_capture.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capture import ScreenCapturer, user32


def main():
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    print("屏幕分辨率: %dx%d" % (sw, sh))

    for w, h in [(640, 480), (960, 720)]:
        cap = ScreenCapturer(0, 0, w, h)
        times = []
        for _ in range(120):
            s = time.perf_counter()
            cap.grab()
            times.append((time.perf_counter() - s) * 1000)
        cap.close()
        avg = sum(times) / len(times)
        budget = 1000.0 / 62.5      # 游戏逻辑 62.5fps(Giuroll f62 版)
        print("%dx%d: 平均 %.2f ms/帧, 最大 %.2f ms/帧 → %s"
              % (w, h, avg, max(times),
                 "62.5fps 预算内(剩 %.1f ms 给感知+决策)" % (budget - avg) if avg < budget
                 else "超出 62.5fps 预算(%.1f ms), 需要缩小捕获区域或换抓屏方案" % avg))


if __name__ == "__main__":
    main()
