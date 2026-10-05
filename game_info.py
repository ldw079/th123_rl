# -*- coding: utf-8 -*-
"""游戏信息诊断(只读): 从游戏窗口找到进程路径, 列出配置/键位相关文件并打印内容。"""

import ctypes
import os
import sys
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from capture import find_windows, user32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.CloseHandle.argtypes = [wintypes.HANDLE]

INTEREST = ("key", "pad", "input", "config", "profile", ".cfg", ".ini", "joystick")


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

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    print("[PID]", pid.value)
    hp = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not hp:
        print("[错误] OpenProcess 失败")
        sys.exit(1)
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    k32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(size))
    k32.CloseHandle(hp)
    exe = buf.value
    print("[EXE]", exe)
    d = os.path.dirname(exe)
    print("[目录]", d)

    hits = []
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x.lower() not in ("th123replay", "replay")]
        for f in files:
            low = f.lower()
            if any(k in low for k in INTEREST):
                hits.append(os.path.join(root, f))
        if len(hits) > 40:
            break
    print("[相关文件]")
    for p in hits:
        print("   ", p)

    print("[文件内容]")
    for p in hits:
        try:
            with open(p, "rb") as fp:
                data = fp.read(4096)
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = repr(data)
            print("--- %s (%d bytes) ---" % (os.path.basename(p), os.path.getsize(p)))
            print(text[:800])
        except Exception as e:
            print("--- %s: 读取失败 %s ---" % (p, e))


if __name__ == "__main__":
    main()
