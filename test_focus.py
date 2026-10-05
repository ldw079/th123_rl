# -*- coding: utf-8 -*-
"""焦点实验: 启动训练实例 → 程序化前台(AttachThreadInput) →
填输入管理器表 → 开局 → 监视调度器激活(mgr.h变化)与场景推进。"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import threading
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client import SokuInstance, CHAR_REIMU  # noqa: E402

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
SCENE = 0x8A0044
MGR = 0x8986A8
TBL = 0x898680

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_hwnd(pid):
    res = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, lparam):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            res.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return res[0] if res else None


def force_foreground(hwnd):
    fg = u32.GetForegroundWindow()
    fg_tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(fg), None)
    this_tid = k32.GetCurrentThreadId()
    tgt_tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), None)
    u32.AttachThreadInput(this_tid, fg_tid, True)
    u32.AttachThreadInput(this_tid, tgt_tid, True)
    u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    u32.AttachThreadInput(this_tid, fg_tid, False)
    u32.AttachThreadInput(this_tid, tgt_tid, False)
    return u32.GetForegroundWindow() == hwnd


def main():
    inst = SokuInstance(20766)
    pid = inst.proc.pid
    h = k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False, pid)
    hwnd = find_hwnd(pid)
    print("PID=%d HWND=%s" % (pid, hwnd and hex(hwnd)))
    time.sleep(1.5)
    ok = force_foreground(hwnd) if hwnd else False
    print("程序化前台: %s" % ("成功" if ok else "失败(可手动点一下游戏窗口)"))

    k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(TBL),
                           struct.pack("<II", 0x8986A8, 0x8986A8), 8, None)

    res = {}

    def _s():
        try:
            inst.start_game(CHAR_REIMU, CHAR_REIMU)
            res["ok"] = 1
        except Exception as e:
            res["err"] = str(e)

    threading.Thread(target=_s, daemon=True).start()

    def rd(a, n):
        b = ctypes.create_string_buffer(n)
        g = ctypes.c_size_t()
        if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(a), b, n,
                                     ctypes.byref(g)):
            return None
        return b.raw

    t0 = time.time()
    kicked = 0
    last = None
    while time.time() - t0 < 45:
        s = rd(SCENE, 1)
        scene = s[0] if s else None
        m = rd(MGR + 0x38, 4)
        mh = struct.unpack("<i", m)[0] if m else None
        if scene != last:
            print("[%4.1fs] scene=%s mgr.h=%s res=%s"
                  % (time.time() - t0, scene, mh, res))
            last = scene
        if scene == 2 and time.time() - t0 > 2 and kicked < 5:
            k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                   b"\x03", 1, None)
            kicked += 1
        if res.get("ok") and scene == 5:
            print("!!! 进战斗 !!!")
            break
        time.sleep(0.15)
    print("最终: res=%s" % res)
    time.sleep(0.5)
    inst.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
