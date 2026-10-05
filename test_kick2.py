# -*- coding: utf-8 -*-
"""踢醒实验v2: 分辨'消息没送达'vs'泵线程阻塞'。
打印 Get/Peek 计数随踢醒的变化 + PostMessage返回值;
对比 PostMessageW(hwnd) / PostThreadMessageW(tid) 两种通路。"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import BridgeCtl, BIT  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

PID = 13916
WM_NULL = 0x0000

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

u32 = ctypes.windll.user32


def find_hwnd(pid):
    from capture import find_windows
    for hwnd, title in find_windows("非想天"):
        p = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            return hwnd
    return None


def main():
    hwnd = find_hwnd(PID)
    tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), None) if hwnd else 0
    print("PID=%d HWND=0x%X TID=%d" % (PID, hwnd or 0, tid))

    sen = HudSensor(PID)
    s = sen.read()
    x0 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    print("P2(右)x0=%s" % x0)

    ctl = BridgeCtl(PID)
    ctl.open_map()

    def snap():
        return (ctl._rd(28), ctl._rd(32), ctl._rd(16), ctl._rd(20), ctl._rd(60))

    a = snap()
    print("起始: Peek=%d Get=%d kb=%d key=%d synth=%d" % a)

    # ① PostMessageW(hwnd) 60次
    ok = 0
    for _ in range(60):
        r = u32.PostMessageW(ctypes.c_void_p(hwnd), WM_NULL, 0, 0)
        ok += 1 if r else 0
        time.sleep(1.0 / 60)
    b = snap()
    print("①PostMsg(hwnd)x60 成功%d: Peek=%d Get=%d kb=%d key=%d synth=%d Δget=%d"
          % (ok, *b, b[1] - a[1]))

    # ② PostThreadMessageW(tid) 60次
    ok = 0
    for _ in range(60):
        r = u32.PostThreadMessageW(tid, WM_NULL, 0, 0)
        ok += 1 if r else 0
        time.sleep(1.0 / 60)
    c = snap()
    print("②PostThreadMsg(tid)x60 成功%d: Peek=%d Get=%d kb=%d key=%d synth=%d Δget=%d"
          % (ok, *c, c[1] - b[1]))

    # ③ SendMessageTimeout 探活(同步通到wndproc)
    res = wt.DWORD_PTR()
    r = u32.SendMessageTimeoutW(ctypes.c_void_p(hwnd), WM_NULL, 0, 0,
                                 0x0002, 500, ctypes.byref(res))  # SMTO_ABORTIFHUNG
    d = snap()
    print("③SendMsgTimeout ret=%s: Peek=%d Get=%d kb=%d key=%d synth=%d"
          % (bool(r), *d))

    if d[2] > 0:
        print("游戏已开始轮询! 继续P2右键测试...")
        ctl.set_keys(BIT["right"])
        t0 = time.time()
        while time.time() - t0 < 1.8:
            u32.PostThreadMessageW(tid, WM_NULL, 0, 0)
            time.sleep(1.0 / 60)
        ctl.release()
        time.sleep(0.3)
        s2 = sen.read()
        x1 = s2["battle"]["right"]["x"] if s2 and s2.get("battle") else None
        print("P2(右)x: %s → %s" % (x0, x1))
    else:
        print("泵仍未运行 — 线程可能阻塞在别处")
    ctl.close()


if __name__ == "__main__":
    main()
