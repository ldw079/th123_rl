# -*- coding: utf-8 -*-
"""传感器验证: 内存读数 vs 视觉读数交叉对照 15 秒(无输入)。"""

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
from capture import find_windows, get_client_rect, make_capturer, user32
from hud_sensor import HudSensor
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
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) if (ctypes := __import__('ctypes')) else None
    x, y, w, h = get_client_rect(hwnd)
    cap = make_capturer(x, y, w, h, scale=config.CAPTURE_SCALE)

    sen = HudSensor(pid.value)
    print("[验证] 15 秒对照采样(无输入)...")
    n_ok = n_bad = 0
    prev_mem = None
    for i in range(150):
        d = sen.read()
        if d is None:
            n_bad += 1
            time.sleep(0.1)
            continue
        _ly, ry_px, _lr, _rr = hp_counts(cap.grab(), cap.w, cap.h)
        if i % 15 == 0:
            b = d["battle"]
            if b:
                print("  场景%d 天气%s(计数%d) 回合%d 状态%d | 内存HP: 左%d 右%d 灵力%d/%d | 视觉右条px=%d"
                      % (d["scene"], d["weather"]["name"], d["weather"]["counter"] or -1,
                         b["round"], b["match_state"],
                         b["left"]["hp"], b["right"]["hp"],
                         b["left"]["spirit"], b["left"]["max_spirit"], ry_px))
            else:
                print("  场景%d 天气%s | 无对局(视觉右条px=%d)"
                      % (d["scene"], d["weather"]["name"], ry_px))
        n_ok += 1
        prev_mem = d
        time.sleep(0.1)
    print("[结果] 读取成功 %d/150, 失败 %d" % (n_ok, n_bad))
    if prev_mem and prev_mem["battle"]:
        print("[判定] 对局数据链通(场景→管理器→角色→血量/灵力)")
    cap.close()
    sen.close()


if __name__ == "__main__":
    main()
