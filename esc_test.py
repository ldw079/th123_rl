# -*- coding: utf-8 -*-
"""ESC 判别测试: 注入 ESC, 看暂停菜单是否弹出。

- ESC 生效(画面巨变) → 注入能到达游戏, 只是移动键不响应 → 键位/手柄配置问题;
- ESC 无反应 → 游戏完全过滤注入输入(exclusive DirectInput)。
测试结束后会再按一次 ESC 尝试恢复(若暂停被触发)。
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
import inject
import loop
from capture import ScreenCapturer, find_windows, get_client_rect
from perception import region_diff


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
    if not loop.wait_foreground(hwnd, seconds=5.0):
        print("[错误] 游戏窗口不在前台")
        sys.exit(1)

    x, y, w, h = get_client_rect(hwnd)
    cap = ScreenCapturer(x, y, w, h)
    time.sleep(0.3)
    a = cap.grab()
    inject.tap(0x1B, hold_s=0.06)   # ESC
    time.sleep(1.2)
    b = cap.grab()
    changed, total = region_diff(a, b, w, h, 0, 0, w, h)
    print("[结果] ESC 前后全画面变化像素: %d (总差异 %d)" % (changed, total))
    if changed > 20000:
        print("[判定] ESC 生效了(暂停菜单应已弹出) → 注入能够到达游戏, 问题在移动键不响应")
        inject.tap(0x1B, hold_s=0.06)   # 再按一次 ESC 恢复
        print("[恢复] 已再按一次 ESC, 请确认游戏是否恢复运行")
    else:
        print("[判定] ESC 无反应 → 注入被游戏完全过滤(exclusive DirectInput)")
    cap.close()


if __name__ == "__main__":
    main()
