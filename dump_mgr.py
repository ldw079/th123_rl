# -*- coding: utf-8 -*-
"""读0x8986A8输入管理器的inKeys/outKeys/readInKeys(训练 vs 40024)。"""
import ctypes
import struct
import sys

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client import SokuInstance  # noqa: E402

k32 = ctypes.windll.kernel32
MGR = 0x8986A8
TBL = 0x898680

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rd(h, a, n):
    b = ctypes.create_string_buffer(n)
    g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(a), b, n,
                                 ctypes.byref(g)):
        return None
    return b.raw


def dump(h, tag):
    tbl = rd(h, TBL, 8)
    m = rd(h, MGR, 0x70)
    if not m:
        print("%s: 读取失败" % tag)
        return
    keys = struct.unpack_from("<H", m, 0x60)[0]
    out = struct.unpack_from("<H", m, 0x62)[0]
    rin = m[0x64]
    hax = struct.unpack_from("<i", m, 0x38)[0]
    vt = struct.unpack_from("<I", m, 0)[0]
    print("%s: 表[0/1]=%s mgr.vtable=0x%X inKeys=0x%04X outKeys=0x%04X "
          "readInKeys=%d h=%d"
          % (tag, tbl.hex() if tbl else "?", vt, keys, out, rin, hax))


def main():
    inst = SokuInstance(20765)
    pid = inst.proc.pid
    h = k32.OpenProcess(0x0410, False, pid)
    dump(h, "训练实例")
    inst.close()
    k32.CloseHandle(ctypes.c_void_p(h))

    h2 = k32.OpenProcess(0x0410, False, 40024)
    if h2:
        dump(h2, "对照40024")
        k32.CloseHandle(ctypes.c_void_p(h2))


if __name__ == "__main__":
    main()
