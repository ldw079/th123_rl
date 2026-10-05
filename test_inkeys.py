# -*- coding: utf-8 -*-
"""KeymapManager注入实验(SokuDev/SokuLib结构):
链: bm(0x8985E4) → +0x0C/+0x10 → CharacterManager → +0x750 → KeyManager
    → +0x00 → KeymapManager { vtable, bindings[13int], [int8], input[10int],
    inKeys/u16, outKeys/u16, readInKeys/bool }
先只读验证(bindings应含DIK扫描码), 再写 inKeys+readInKeys 驱动P1。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400

BATTLE_MGR = 0x8985E4
INPUT_MGR_CLUSTER = 0x89A248
OFS_INPUT = 0x58      # KeyInput(10int): h/v/a/b/c/d/cc/sc/pause/select
OFS_INKEYS = 0x80
OFS_READIN = 0x84

DIK = {0x11: "W", 0x1E: "A", 0x1F: "S", 0x20: "D", 0x17: "I", 0x16: "U",
       0x18: "O", 0x24: "J", 0x25: "K", 0x26: "L"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rpm(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                 buf, n, ctypes.byref(got)) or got.value != n:
        return None
    return buf.raw


def wpm(h, addr, data):
    got = ctypes.c_size_t()
    return bool(k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                       data, len(data), ctypes.byref(got)))


def u32(h, a):
    r = rpm(h, a, 4)
    return struct.unpack("<I", r)[0] if r else None


def ptr(v):
    return v is not None and 0x10000 <= v < 0x80000000


def get_keymap_mgrs(h):
    bm = u32(h, BATTLE_MGR)
    if not ptr(bm):
        return None, None, None
    out = []
    for ofs in (0x0C, 0x10):
        cm = u32(h, bm + ofs)
        if not ptr(cm):
            return bm, None, None
        kmgr = u32(h, cm + 0x750)
        if not ptr(kmgr):
            return bm, cm, None
        kmap = u32(h, kmgr)          # KeyManager+0x00 = keymapManager*
        out.append(kmap if ptr(kmap) else None)
    return bm, out[0], out[1]


def dump_km(h, tag, km):
    raw = rpm(h, km, 0x90)
    if not raw:
        print("%s km=0x%X 读取失败" % (tag, km))
        return
    vt = struct.unpack_from("<I", raw, 0)[0]
    binds = struct.unpack_from("<13I", raw, 4)
    named = [DIK.get(v, v) for v in binds]
    inp = struct.unpack_from("<10i", raw, OFS_INPUT)
    inkeys = struct.unpack_from("<H", raw, OFS_INKEYS)
    readin = raw[OFS_READIN]
    print("%s KeymapMgr@0x%X vtable=0x%X" % (tag, km, vt))
    print("   bindings: %s" % named)
    print("   input(h,v,a,b,c,d,cc,sc,pause,sel)=%s inKeys=0x%04X readIn=%d"
          % (list(inp), inkeys[0], readin))


def p1x(sen):
    s = sen.read()
    return s["battle"]["left"]["x"] if s and s.get("battle") else None


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    if not h:
        print("OpenProcess失败")
        return
    sen = HudSensor(pid)

    bm, kml, kmr = get_keymap_mgrs(h)
    print("bm=0x%s kmL=0x%s kmR=0x%s" % (bm and hex(bm), kml and hex(kml),
                                         kmr and hex(kmr)))
    if not (ptr(kml) and ptr(kmr)):
        print("!! 链路断裂")
        return
    dump_km(h, "P1", kml)
    dump_km(h, "P2", kmr)

    # 集群对照
    cl = rpm(h, INPUT_MGR_CLUSTER, 0x20)
    if cl:
        print("cluster@0x89A248: %s" % cl.hex())

    # 实验: readInKeys=1 + inKeys=右(0x08) 持续1.5s
    x0 = p1x(sen)
    print("\nP1x=%s, 写 inKeys=0x08 + readInKeys=1 (1.5s)..." %
          (round(x0) if x0 else None))
    t_end = time.time() + 1.5
    n = 0
    while time.time() < t_end:
        wpm(h, kml + OFS_INKEYS, struct.pack("<H", 0x0008))
        wpm(h, kml + OFS_READIN, b"\x01")
        n += 1
        time.sleep(1.0 / 120)
    wpm(h, kml + OFS_INKEYS, struct.pack("<H", 0))
    wpm(h, kml + OFS_READIN, b"\x00")
    time.sleep(0.3)
    x1 = p1x(sen)
    d = (x1 - x0) if (x1 is not None and x0 is not None) else None
    print("结果: P1x=%s Δ=%s %s" % (round(x1) if x1 else None,
                                    round(d) if d is not None else None,
                                    "<<< 成功!!!" if d and d > 5 else ""))

    if not (d and d > 5):
        # 回退实验: 直接写input计数器(horizontalAxis每帧+1)
        x0 = p1x(sen)
        print("回退: 写input.horizontalAxis递增 (1.5s)...")
        cnt = 0
        t_end = time.time() + 1.5
        while time.time() < t_end:
            cnt += 1
            wpm(h, kml + OFS_INPUT, struct.pack("<i", cnt))
            time.sleep(1.0 / 120)
        wpm(h, kml + OFS_INPUT, struct.pack("<i", 0))
        time.sleep(0.3)
        x1 = p1x(sen)
        d = (x1 - x0) if (x1 is not None and x0 is not None) else None
        print("结果: P1x=%s Δ=%s %s" % (round(x1) if x1 else None,
                                        round(d) if d is not None else None,
                                        "<<< 成功!!!" if d and d > 5 else ""))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
