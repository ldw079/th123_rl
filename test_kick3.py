# -*- coding: utf-8 -*-
"""踢醒实验v3: active=1先行(让GetForegroundWindow谎言生效) → 踢醒 → P2位移。"""
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


def kick(hwnd, tid, seconds):
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds:
        u32.PostThreadMessageW(tid, WM_NULL, 0, 0)
        u32.PostMessageW(ctypes.c_void_p(hwnd), WM_NULL, 0, 0)
        n += 1
        time.sleep(1.0 / 90)
    return n


def main():
    hwnd = find_hwnd(PID)
    tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), None)
    print("PID=%d HWND=0x%X TID=%d" % (PID, hwnd or 0, tid))

    sen = HudSensor(PID)
    s = sen.read()
    x0 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    print("P2(右)x0=%s" % x0)

    ctl = BridgeCtl(PID)
    ctl.open_map()

    # active=1 + hwnd + 激活请求
    ctl._wr(44, hwnd)
    ctl._wr(48, 1)
    ctl._wr(8, 1)
    print("active=1 hwnd=0x%X, 踢醒2s..." % hwnd)
    n = kick(hwnd, tid, 2.0)
    kb1 = ctl._rd(16)
    key1 = ctl._rd(20)
    print("踢了%d次: kbstate=%d keystate=%d synth=%d" % (n, kb1, key1, ctl._rd(60)))

    if kb1 == 0:
        print("kbstate=0 — 游戏核心可能是事件驱动, 直接测事件路径:")

    print("轮询已开始! P2右键1.8s(持续踢醒)...")
    ctl.set_keys(BIT["right"])
    kick(hwnd, tid, 1.8)
    ctl.release()
    time.sleep(0.3)
    s2 = sen.read()
    x1 = s2["battle"]["right"]["x"] if s2 and s2.get("battle") else None
    print("P2(右)x: %s → %s | kb=%d key=%d synth=%d"
          % (x0, x1, ctl._rd(16), ctl._rd(20), ctl._rd(60)))
    if x1 is not None and x0 is not None and abs(x1 - x0) > 1.0:
        print(">>> 成功! 后台P2动了!")
    else:
        print(">>> 角色未动 — 轮询在但状态未被采用, 需事件路径")
    ctl.close()


if __name__ == "__main__":
    main()
