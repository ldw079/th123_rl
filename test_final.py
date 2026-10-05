# -*- coding: utf-8 -*-
"""三连确认: ①P1驱动 ②P2按键(A=J打击) ③输入源[1]写入必要性A/B。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
TBL1 = 0x898684
DUMMY = 0x8986A8

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

k32 = ctypes.windll.kernel32


def rpm(h, a, n):
    b = ctypes.create_string_buffer(n)
    g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(a), b, n,
                                 ctypes.byref(g)) or g.value != n:
        return None
    return b.raw


def wpm(h, a, d):
    g = ctypes.c_size_t()
    return bool(k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(a),
                                       d, len(d), ctypes.byref(g)))


def state(sen):
    s = sen.read()
    if not s or not s.get("battle"):
        return None
    return s["battle"]


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    sen = HudSensor(pid)
    ctl = BridgeCtl(pid)
    ctl.open_map()
    calls0 = ctl._rd(20)
    time.sleep(0.5)
    calls1 = ctl._rd(20)
    print("detour活性: Δ=%d/0.5s" % (calls1 - calls0))
    if calls1 == calls0:
        print("!! 回合不活, 退出")
        return

    # ① P1驱动
    b = state(sen)
    x0 = b["left"]["x"]
    ctl._wr(0, 0x08)   # p1 right
    ctl._wr(16, 1)
    time.sleep(1.5)
    ctl._wr(0, 0)
    time.sleep(0.3)
    b = state(sen)
    d = b["left"]["x"] - x0 if b else None
    print("①P1右: %.0f→%s Δ=%s %s" % (x0, b and round(b["left"]["x"]),
                                       d and round(d),
                                       "OK" if d and abs(d) > 5 else "(未动)"))

    # ② P2 A键(打击): 看P2 action变化
    b = state(sen)
    act0 = b["right"]["action"] if b else None
    ctl._wr(8, 0x10)   # p2 A
    ctl._wr(16, 1)
    time.sleep(1.2)
    ctl._wr(8, 0)
    time.sleep(0.3)
    b = state(sen)
    act1 = b["right"]["action"] if b else None
    print("②P2 A键: action %s→%s %s" % (act0, act1,
          "OK" if act0 != act1 else "(action未变 — 萃香可能没到攻击态)"))

    # ③ 输入源[1] A/B测试
    wpm(h, TBL1, struct.pack("<I", 0))
    print("③[1]置0后测P2右...")
    time.sleep(0.5)
    b = state(sen)
    x0 = b["right"]["x"] if b else None
    ctl._wr(8, 0x08)
    ctl._wr(16, 1)
    time.sleep(1.2)
    ctl._wr(8, 0)
    time.sleep(0.3)
    b = state(sen)
    x1 = b["right"]["x"] if b else None
    d = (x1 - x0) if (x1 is not None and x0 is not None) else None
    print("  [1]=0时 P2右 Δ=%s %s" % (d and round(d),
          "(仍动 → 写入非必需)" if d and abs(d) > 5 else "(不动 → 写入必需)"))
    wpm(h, TBL1, struct.pack("<I", DUMMY))
    print("  [1]已恢复0x%X" % DUMMY)
    ctl.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40024)
