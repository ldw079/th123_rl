# -*- coding: utf-8 -*-
"""keybd_event注入链路系统性最小验证: 记事本收不到注入键=系统级封锁。"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import inject  # noqa: E402

u32 = ctypes.windll.user32


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    # 找记事本窗口
    hwnd = None
    for _ in range(20):
        hwnd = u32.FindWindowW("Notepad", None)
        if hwnd:
            break
        time.sleep(0.2)
    if not hwnd:
        print("没找到记事本窗口")
        p.kill()
        return
    u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    time.sleep(0.6)
    fg = u32.GetForegroundWindow()
    print("记事本HWND=0x%X 前台=%s" % (hwnd, fg == hwnd))

    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 256)
    t0 = buf.value
    print("标题前: %r" % t0)

    inject.tap(0x41, 0.08)   # A
    time.sleep(0.3)
    inject.tap(0x42, 0.08)   # B
    time.sleep(1.0)

    u32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 256)
    t1 = buf.value
    print("标题后: %r" % t1)
    if t1 != t0 and "*" in t1:
        print(">>> 注入键到达记事本(标题变脏) — 注入链路正常")
    else:
        print(">>> 注入键没到达 — 系统级注入被封锁(UIPI/权限/安全软件)")
    p.kill()


if __name__ == "__main__":
    main()
