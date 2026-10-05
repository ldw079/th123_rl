# -*- coding: utf-8 -*-
"""自检脚本(不需要游戏): 验证"抓屏 + 键盘注入"链路是否可用。

流程:
  1. 全屏抓 30 帧, 统计耗时(验证抓屏);
  2. 启动记事本 → 注入一段文本 → 对比画面变化(验证注入);
  3. 关闭记事本(由本脚本启动, 由本脚本关闭)。

运行: python selftest.py
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from capture import ScreenCapturer, find_windows, get_client_rect, user32
from inject import tap
from perception import region_diff

TEXT = "TH123-RL-OK"
WM_CLOSE = 0x0010
CHAR_VK = {chr(ord("A") + i): 0x41 + i for i in range(26)}
CHAR_VK.update({str(i): 0x30 + i for i in range(10)})
CHAR_VK["-"] = 0x0BD


def main():
    print("== 测试 1: 抓屏性能(全屏 30 帧) ==")
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    cap = ScreenCapturer(0, 0, sw, sh)
    times = []
    for _ in range(30):
        s = time.perf_counter()
        cap.grab()
        times.append((time.perf_counter() - s) * 1000)
    cap.close()
    avg = sum(times) / len(times)
    print("  平均 %.2f ms/帧, 最大 %.2f ms/帧 → %s" % (avg, max(times), "通过" if avg < 12 else "偏慢但可用"))

    print("== 测试 2: 键盘注入(记事本往返) ==")
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = None
    for _ in range(30):
        time.sleep(0.5)
        wins = find_windows("记事本") or find_windows("Notepad")
        if wins:
            hwnd = wins[0][0]
            break
    if not hwnd:
        print("  找不到记事本窗口(标题不匹配), 注入测试跳过")
        try:
            proc.terminate()
        except Exception:
            pass
        print("== 自检结束(测试 2 跳过) ==")
        return

    fg = False
    for _ in range(10):
        if user32.GetForegroundWindow() == hwnd:
            fg = True
            break
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    if not fg:
        print("  记事本未能自动置前, 等待 3 秒; 若仍未置前请手动点击记事本窗口...")
        time.sleep(3)
        fg = user32.GetForegroundWindow() == hwnd
    if not fg:
        print("  记事本仍不在前台, 注入测试跳过(不影响抓屏结论)")
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.5)
        if user32.IsWindow(hwnd):
            try:
                proc.kill()
            except Exception:
                pass
        print("== 自检结束(测试 2 跳过) ==")
        return

    time.sleep(0.3)
    x, y, w, h = get_client_rect(hwnd)
    c2 = ScreenCapturer(x, y, w, h)
    before = c2.grab()
    for ch in TEXT:
        tap(CHAR_VK[ch], hold_s=0.04)
        time.sleep(0.05)
    time.sleep(0.4)
    after = c2.grab()
    c2.close()
    changed, _ = region_diff(before, after, w, h, 0, 0, w, h)
    ok = changed > 50
    print("  注入 %r 前后客户区变化像素: %d → %s"
          % (TEXT, changed, "通过: 注入确实改变了画面" if ok else "未通过: 画面无变化, 请检查前台焦点"))

    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.8)
    if user32.IsWindow(hwnd):
        tap(0x1B, hold_s=0.05)      # 若弹出"是否保存", 按 ESC 取消
        time.sleep(0.5)
        if user32.IsWindow(hwnd):
            try:
                proc.kill()
            except Exception:
                pass
    print("== 自检完成 ==")


if __name__ == "__main__":
    main()
