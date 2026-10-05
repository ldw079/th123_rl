# -*- coding: utf-8 -*-
"""被动观测: 不注入任何输入, 10Hz 采样双 HP 条 15 秒, 打印波动事件。
用于回答: 没有攻击时, 血条读数会不会自己变化(天气色调/回合重置/遮挡)? """

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
from perception import hp_counts


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

    prev = None
    events = 0
    t0 = time.perf_counter()
    print("[观测] 15 秒, 无任何输入...")
    while time.perf_counter() - t0 < 15.0:
        ly, ry, lr, rr = hp_counts(cap.grab(), cap.w, cap.h)
        if prev is not None:
            dly, dry = ly - prev[0], ry - prev[1]
            if abs(dly) >= 10 or abs(dry) >= 10:
                events += 1
                print("  t=%.1fs  左(己)%+d → %d   右(敌)%+d → %d" % (
                    time.perf_counter() - t0, dly, ly, dry, ry))
        prev = (ly, ry)
        time.sleep(0.1)
    ly, ry = prev
    print("[结论] 15 秒内 %d 次波动; 末值: 左=%d 右=%d (若波动>0, 奖励信号含结构性噪声)"
          % (events, ly, ry))
    cap.close()


if __name__ == "__main__":
    main()
