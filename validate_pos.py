# -*- coding: utf-8 -*-
"""验证扩展传感器: 坐标/速度/朝向/动作 与 视觉追踪对照。"""

import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
import loop
from capture import find_windows, user32
from hud_sensor import HudSensor


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
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) if (ctypes := __import__('ctypes')) else None
    sen = HudSensor(pid.value)
    print("[验证] 10 秒坐标流(无输入):")
    for i in range(20):
        d = sen.read()
        if d and d["battle"]:
            b = d["battle"]
            l, r = b["left"], b["right"]
            print("  帧%-6d 左(x=%.0f y=%.0f vx=%.1f vy=%.1f 面%d 动作%d) 右(x=%.0f y=%.0f 动作%d)"
                  % (b["frame"], l["x"], l["y"], l["vx"], l["vy"],
                     l["facing"] or 0, l["action"] or 0,
                     r["x"], r["y"], r["action"] or 0))
        time.sleep(0.5)
    sen.close()


if __name__ == "__main__":
    main()
