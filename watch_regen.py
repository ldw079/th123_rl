# -*- coding: utf-8 -*-
"""被动观测回血: 不注入任何输入, 20 秒内监测对手血条是否自发回升(练习模式自动回血?)。
同时打印每次变化的幅度与方向, 供奖励设计参考。"""

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
from capture import make_capturer, find_windows, get_client_rect
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
    cap = make_capturer(x, y, w, h, scale=config.CAPTURE_SCALE)

    prev = None
    rises = drops = 0
    t0 = time.perf_counter()
    print("[观测] 20 秒, 无任何输入 — 监测对手血条自发变化...")
    peak = 0
    while time.perf_counter() - t0 < 20.0:
        _ly, ry, _lr, _rr = hp_counts(cap.grab(), cap.w, cap.h)
        if prev is not None:
            d = ry - prev
            if d >= 15:
                rises += 1
                print("  t=%.1fs 对手血条 +%d (回升→ %d)" % (time.perf_counter() - t0, d, ry))
            elif d <= -15:
                drops += 1
                print("  t=%.1fs 对手血条 %d (下降→ %d)" % (time.perf_counter() - t0, d, ry))
        prev = ry
        peak = max(peak, ry)
        time.sleep(0.1)
    print("[结论] 20 秒内: 自发回升 %d 次, 下降 %d 次; 峰值 %d, 末值 %d"
          % (rises, drops, peak, prev))
    if rises > 2 and prev >= 0.9 * peak:
        print("[判定] 存在自动回血 → 每次伤害会被回血稀释, 小伤害可能掉进噪声阈值以下")
    elif rises == 0:
        print("[判定] 无自动回血 → 奖励不受回血影响")
    else:
        print("[判定] 偶发波动(%d 次), 可能是天气色调, 需结合画面判断" % rises)
    cap.close()


if __name__ == "__main__":
    main()
