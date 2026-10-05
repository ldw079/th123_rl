# -*- coding: utf-8 -*-
"""输入源激活实验(SokuAI startGame复刻):
读 0x898680 指针表/主副模式 → 写 0x8986A8 到 [0]/[1] → 看v8 detour calls
是否点亮 → 立即测P2右移。全部外部读写, 4字节有界。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
TBL = 0x898680
DUMMY = 0x8986A8
MAIN_MODE = 0x898690   # ADDR_COMM_MODE
SUB_MODE = 0x898688    # ADDR_SUB_MODE

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


def u32(h, a):
    r = rpm(h, a, 4)
    return struct.unpack("<I", r)[0] if r else None


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    sen = HudSensor(pid)
    ctl = BridgeCtl(pid)
    ctl.open_map()   # v8已注入(上次跑过test_v8)

    raw = rpm(h, TBL, 0x40)
    print("0x898680区: %s" % (raw.hex() if raw else None))
    print("[0]=0x%X [1]=0x%X mainMode(0x898690)=%s subMode(0x898688)=%s"
          % (u32(h, TBL) or 0, u32(h, TBL + 4) or 0,
             u32(h, MAIN_MODE), u32(h, SUB_MODE)))

    c1 = ctl._rd(20)
    print("\nv8 calls当前=%d" % c1)

    # 写输入源(两个槽都指向dummy包装, SokuAI只写[1], 我们双喂写两个)
    wpm(h, TBL, struct.pack("<I", DUMMY))
    wpm(h, TBL + 4, struct.pack("<I", DUMMY))
    print("已写 [0]=[1]=0x%X" % DUMMY)
    time.sleep(2.0)
    c2 = ctl._rd(20)
    print("2秒后 calls=%d (Δ=%d)" % (c2, c2 - c1))

    if c2 == c1:
        print("!! detour仍未触发")
        # 尝试同时写主副模式(VSPLAYER=3, PLAYING2=1)
        wpm(h, MAIN_MODE, struct.pack("<I", 3))
        wpm(h, SUB_MODE, struct.pack("<I", 1))
        print("已写 mainMode=3 subMode=1, 再等2s")
        time.sleep(2.0)
        c3 = ctl._rd(20)
        print("calls=%d (Δ=%d)" % (c3, c3 - c2))
        if c3 == c2:
            print("!! 仍未触发 — 输入路径激活需要更多SokuAI初始化")
            return

    # 触发了! 立即测P2
    s = sen.read()
    x2_0 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    print("\nP2(右)按右1.8s... P2x=%s" % (round(x2_0) if x2_0 else None))
    ctl._wr(8, 0x08)
    ctl._wr(16, 1)
    time.sleep(1.8)
    ctl._wr(8, 0)
    time.sleep(0.3)
    s = sen.read()
    x2_1 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    d = (x2_1 - x2_0) if (x2_1 is not None and x2_0 is not None) else None
    print("P2x: %s→%s Δ=%s %s" % (round(x2_0) if x2_0 else None,
                                   round(x2_1) if x2_1 else None,
                                   round(d) if d is not None else None,
                                   "<<< 成功!!!" if d and abs(d) > 5 else ""))
    ctl.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40024)
