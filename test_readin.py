# -*- coding: utf-8 -*-
"""readInKeys输入源切换实验: km+0x60=inKeys(u16), km+0x64=readInKeys(bool)。
设readInKeys=1 + 写inKeys位 → 看是否驱动。零DLL纯外部。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
BATTLE_MGR = 0x8985E4
# BattleKeys: 1=up 2=down 4=left 8=right 0x10=A 0x20=B 0x40=C 0x80=dash

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


def kmaps(h):
    bm = u32(h, BATTLE_MGR)
    out = []
    for ofs in (0x0C, 0x10):
        cm = u32(h, bm + ofs)
        kmgr = u32(h, cm + 0x750)
        km = u32(h, kmgr)
        out.append(km if 0x10000 < km < 0x80000000 else None)
    return out


def drive(h, sen, km, name, bits, seconds):
    s = sen.read()
    x0 = s["battle"][name]["x"]
    wpm(h, km + 0x64, b"\x01")                     # readInKeys=1
    wpm(h, km + 0x60, struct.pack("<H", bits))     # inKeys=bits
    time.sleep(seconds)
    wpm(h, km + 0x60, struct.pack("<H", 0))
    wpm(h, km + 0x64, b"\x00")
    time.sleep(0.3)
    s = sen.read()
    x1 = s["battle"][name]["x"]
    d = x1 - x0
    print("%s bits=0x%02X: %.0f→%.0f Δ=%.0f %s"
          % (name, bits, x0, x1, d, "<<<动!" if abs(d) > 5 else "(未动)"))
    return abs(d) > 5


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    sen = HudSensor(pid)
    kmL, kmR = kmaps(h)
    print("kmL=%s kmR=%s" % (kmL and hex(kmL), kmR and hex(kmR)))

    ok = drive(h, sen, kmR, "right", 0x0008, 1.5)      # P2右
    if not ok:
        # 也许readInKeys清掉了inKeys? 持续重写试试
        print("持续重写模式...")
        s = sen.read()
        x0 = s["battle"]["right"]["x"]
        wpm(h, kmR + 0x64, b"\x01")
        n = 0
        t_end = time.time() + 1.5
        while time.time() < t_end:
            wpm(h, kmR + 0x60, struct.pack("<H", 0x0008))
            n += 1
            time.sleep(1.0 / 200)
        wpm(h, kmR + 0x60, struct.pack("<H", 0))
        wpm(h, kmR + 0x64, b"\x00")
        time.sleep(0.3)
        s = sen.read()
        x1 = s["battle"]["right"]["x"]
        d = x1 - x0
        print("P2持续重写%d次: Δ=%.0f %s" % (n, d, "<<<动!" if abs(d) > 5 else "(仍未动)"))
    drive(h, sen, kmL, "left", 0x0008, 1.5)            # P1右
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30740)
