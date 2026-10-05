# -*- coding: utf-8 -*-
"""传感器原始数据对比: SokuLib链(0x8985E4) vs 神AI链(0x6E6244) vs 天气计数器。
判定哪一环在说谎。只读。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

SCENE = 0x8A0044
WEATHER = 0x8971C0
WCOUNTER = 0x8971CC
BATTLE_MGR_SOKU = 0x8985E4
SWR_SCENEID = 0x6ECE7C
SWR_BATTLEMGR = 0x6E6244
SWR_KEYMAP1P = 0x6E6598
SWR_LCHARID = 0x6E6FF0
SWR_RCHARID = 0x6E7010

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rpm(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr), buf, n,
                                 ctypes.byref(got)) or got.value != n:
        return None
    return buf.raw


def u32(h, a):
    r = rpm(h, a, 4)
    return struct.unpack("<I", r)[0] if r else None


def u16(h, a):
    r = rpm(h, a, 2)
    return struct.unpack("<H", r)[0] if r else None


def u8(h, a):
    r = rpm(h, a, 1)
    return r[0] if r else None


def f32(h, a):
    r = rpm(h, a, 4)
    return struct.unpack("<f", r)[0] if r else None


def ptr(v):
    return v is not None and 0x10000 <= v < 0x80000000


def dump_chain(h, tag, mgr):
    """按SokuLib偏移走一条mgr链, 打印frame/HP/x原始值。"""
    if not ptr(mgr):
        print("  %s mgr指针无效 0x%s" % (tag, mgr))
        return
    lc, rc = u32(h, mgr + 0x0C), u32(h, mgr + 0x10)
    print("  %s mgr=0x%X frame=%s state=%s round=%s L=0x%X R=0x%X"
          % (tag, mgr, u32(h, mgr + 4), u8(h, mgr + 0x88), u8(h, mgr + 0x904),
             lc or 0, rc or 0))
    for nm, c in (("L", lc), ("R", rc)):
        if ptr(c):
            print("    %s: hp=%s x=%s y=%s act=%s"
                  % (nm, struct.unpack("<h", rpm(h, c + 0x184, 2) or b"\0\0")[0],
                     round(f32(h, c + 0xEC), 1), round(f32(h, c + 0xF0), 1),
                     u16(h, c + 0x13C)))


def main(pid):
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print("OpenProcess失败")
        return
    for i in range(3):
        print("=== PID=%d 采样#%d" % (pid, i))
        print("  scene(soku)=%s scene(swr)=%s weather=%s wcount=%s"
              % (u8(h, SCENE), u8(h, SWR_SCENEID), u8(h, WEATHER), u16(h, WCOUNTER)))
        print("  charid L/R(swr)=%s/%s keymap1P前16字节=%s"
              % (u8(h, SWR_LCHARID), u8(h, SWR_RCHARID),
                 (rpm(h, SWR_KEYMAP1P, 16) or b"").hex()))
        p1 = u32(h, BATTLE_MGR_SOKU)
        dump_chain(h, "soku", p1)
        dump_chain(h, "soku**", u32(h, p1) if ptr(p1) else None)
        dump_chain(h, "swr  ", u32(h, SWR_BATTLEMGR))
        time.sleep(1.5)
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 39208)
