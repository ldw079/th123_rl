# -*- coding: utf-8 -*-
"""只读: 转储目标进程内user32键盘函数的前32字节机器码。
用于判断inline hook可行性(是否热补丁桩/简单syscall stub)。"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import list_modules, rpm, export_rva  # noqa: E402

k32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

FUNCS = ["GetKeyboardState", "GetAsyncKeyState", "GetKeyState", "GetFocus",
         "GetForegroundWindow"]


def main():
    from capture import find_windows
    u32 = ctypes.windll.user32
    seen = set()
    for hwnd, title in find_windows("非想天"):
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in seen or not pid.value:
            continue
        seen.add(pid.value)
        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid.value)
        if not h:
            continue
        mods = list_modules(pid.value)
        u32base = mods.get("user32.dll")
        print("PID=%d user32=0x%X" % (pid.value, u32base))
        for fn in FUNCS:
            rva = export_rva(h, u32base, fn)
            if not rva:
                print("  %-20s <无导出>" % fn)
                continue
            code = rpm(h, u32base + rva, 32)
            hexs = " ".join("%02X" % b for b in code) if code else "<读取失败>"
            print("  %-20s +0x%-5X %s" % (fn, rva, hexs))
        k32.CloseHandle(ctypes.c_void_p(h))
        break  # 一个实例够了


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
