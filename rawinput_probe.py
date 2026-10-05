# -*- coding: utf-8 -*-
"""探针: SendInput 注入的键盘事件会不会出现在 Raw Input 流里。

原理: 本进程注册键盘原始输入设备(RIDEV_INPUTSINK, 非前台也能收),
然后 SendInput 注入按键, 统计收到的 WM_INPUT 条数。
- 收到 0 条 → 系统在 Raw Input 层过滤注入事件 → 用 Raw Input 读键盘的游戏看不到注入按键;
- 收到 >0 条 → 注入事件能进 Raw Input, 问题在别处。
"""

import ctypes
import sys
import time
from ctypes import wintypes

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

from inject import tap

WM_INPUT = 0x00FF
WM_QUIT = 0x0012
RIDEV_INPUTSINK = 0x00000100

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT,
                                           wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DestroyWindow.argtypes = [wintypes.HWND]
kernel32.GetLastError.restype = wintypes.DWORD

count = {"wm_input": 0}


@WNDPROC
def wndproc(hwnd, msg, wp, lp):
    if msg == WM_INPUT:
        count["wm_input"] += 1
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


def pump(seconds):
    msg = wintypes.MSG()
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.002)


def main():
    cls = WNDCLASSW()
    cls.lpfnWndProc = wndproc
    cls.hInstance = kernel32.GetModuleHandleW(None)
    cls.lpszClassName = "RawInputProbe"
    if not user32.RegisterClassW(ctypes.byref(cls)):
        print("[错误] RegisterClassW 失败, err=", kernel32.GetLastError())
        sys.exit(1)
    hwnd = user32.CreateWindowExW(0, "RawInputProbe", "probe", 0, 0, 0, 0, 0,
                                  0, 0, cls.hInstance, None)
    print("[信息] 探针窗口:", hwnd)

    rid = RAWINPUTDEVICE()
    rid.usUsagePage = 0x01      # Generic Desktop
    rid.usUsage = 0x06          # Keyboard
    rid.dwFlags = RIDEV_INPUTSINK
    rid.hwndTarget = hwnd
    ok = user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
    print("[信息] RegisterRawInputDevices:", bool(ok), "err=", kernel32.GetLastError())

    time.sleep(0.5)
    pump(0.5)   # 清空注册前积压的消息
    n0 = count["wm_input"]

    for _ in range(5):
        tap(0x57, hold_s=0.05)   # W
        time.sleep(0.15)
    pump(1.0)
    n1 = count["wm_input"]
    print("[结果] 注入 5 次按键, Raw Input 收到的 WM_INPUT 条数: %d (注入前 %d)" % (n1 - n0, n0))
    if n1 == n0:
        print("[结论] Raw Input 完全收不到注入事件 → 系统层面过滤, 走 Raw Input 读键盘的游戏看不到注入按键")
    else:
        print("[结论] Raw Input 能收到注入事件 → 游戏应能看到注入按键, 问题不在这一层")
    user32.DestroyWindow(hwnd)


if __name__ == "__main__":
    main()
