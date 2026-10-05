# -*- coding: utf-8 -*-
"""快速检查: 游戏窗口在不在, 血条读数多少(判断是否在对局画面)。"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
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
        print("[结果] 游戏窗口不存在(游戏已关闭?)")
        return
    hwnd, title = win
    print("[结果] 游戏窗口在:", title)
    x, y, w, h = get_client_rect(hwnd)
    cap = ScreenCapturer(x, y, w, h, scale=2)
    time.sleep(0.3)
    ly, ry, _lr, _rr = hp_counts(cap.grab(), cap.w, cap.h)
    cap.close()
    print("[结果] 左(己)黄=%d 右(敌)黄=%d → %s" % (
        ly, ry, "对局画面(可训练)" if ry >= 500 else "非对局画面(菜单/暂停/过场)"))


if __name__ == "__main__":
    main()
