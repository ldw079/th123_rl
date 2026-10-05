# -*- coding: utf-8 -*-
"""信箱输入验证(零DLL): km+0x38每帧被清零 → 外部120Hz持续写计数器。
P2右1.5s → P1右1.5s。纯Python内存写, 若成则输入方案彻底摆脱DLL。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
BATTLE_MGR = 0x8985E4

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


def hold(h, km, field_off, direction, seconds):
    """按住某方向/键: 200Hz持续写信箱计数器(每写一次+1)"""
    n = 0
    t_end = time.time() + seconds
    while time.time() < t_end:
        n += 1
        wpm(h, km + field_off, struct.pack("<i", direction * n))
        time.sleep(1.0 / 200)
    wpm(h, km + field_off, struct.pack("<i", 0))


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    sen = HudSensor(pid)
    kmL, kmR = kmaps(h)
    print("kmL=%s kmR=%s" % (kmL and hex(kmL), kmR and hex(kmR)))
    if not (kmL and kmR):
        return

    # P2 右
    s = sen.read()
    x0 = s["battle"]["right"]["x"]
    print("P2右1.5s (信箱200Hz)...")
    hold(h, kmR, 0x38, 1, 1.5)
    time.sleep(0.3)
    s = sen.read()
    x1 = s["battle"]["right"]["x"]
    d = x1 - x0
    print("P2x: %.0f→%.0f Δ=%.0f %s" % (x0, x1, d, "<<<成功!" if abs(d) > 5 else "(未动)"))

    # P1 右
    s = sen.read()
    x0 = s["battle"]["left"]["x"]
    print("P1右1.5s...")
    hold(h, kmL, 0x38, 1, 1.5)
    time.sleep(0.3)
    s = sen.read()
    x1 = s["battle"]["left"]["x"]
    d = x1 - x0
    print("P1x: %.0f→%.0f Δ=%.0f %s" % (x0, x1, d, "<<<成功!" if abs(d) > 5 else "(未动)"))

    # P1 左(负向验证)
    s = sen.read()
    x0 = s["battle"]["left"]["x"]
    print("P1左1.2s...")
    hold(h, kmL, 0x38, -1, 1.2)
    time.sleep(0.3)
    s = sen.read()
    x1 = s["battle"]["left"]["x"]
    d = x1 - x0
    print("P1x: %.0f→%.0f Δ=%.0f %s" % (x0, x1, d, "<<<成功!" if d < -5 else "(未动)"))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30740)
