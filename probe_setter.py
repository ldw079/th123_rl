# -*- coding: utf-8 -*-
"""无猜测三探: ①input清零探针(设置器是否在运行) ②三实例模式对比
③30740原始E8操作数=真正SetInputs实现地址。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
BATTLE_MGR = 0x8985E4
MAIN_MODE = 0x898690
SUB_MODE = 0x898688
THUNK = 0x40A45D

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
    if not bm or not (0x10000 < bm < 0x80000000):
        return out
    for ofs in (0x0C, 0x10):
        cm = u32(h, bm + ofs)
        if not cm or not (0x10000 < cm < 0x80000000):
            out.append(None)
            continue
        kmgr = u32(h, cm + 0x750)
        km = u32(h, kmgr) if kmgr and 0x10000 < kmgr < 0x80000000 else 0
        out.append(km if km and 0x10000 < km < 0x80000000 else None)
    return out


def main():
    # ② 模式对比 + ③ 原始操作数
    for pid in (30740, 40024, 39208):
        try:
            h = k32.OpenProcess(RWX, False, pid)
        except OSError:
            continue
        if not h:
            continue
        code = rpm(h, THUNK, 5)
        operand = struct.unpack("<i", code[1:5])[0] if code and code[0] == 0xE8 else None
        target = (THUNK + 5 + operand) if operand is not None else None
        km = kmaps(h)
        print("PID=%d mainMode=%s subMode=%s kmL=%s kmR=%s call目标=%s"
              % (pid, u32(h, MAIN_MODE), u32(h, SUB_MODE),
                 km[0] and hex(km[0]), km[1] and hex(km[1]),
                 target and hex(target)))
        k32.CloseHandle(ctypes.c_void_p(h))

    # ① 清零探针(30740)
    h = k32.OpenProcess(RWX, False, 30740)
    if not h:
        print("30740打开失败")
        return
    km = kmaps(h)
    if not km or not km[0]:
        print("30740链路不通")
        return
    target = km[0] + 0x38
    print("\n探针: 写h=7到kmL+0x38 (0x%X)..." % target)
    wpm(h, target, struct.pack("<i", 7))
    cleared_t = None
    t0 = time.time()
    while time.time() - t0 < 1.0:
        v = u32(h, target)
        if v == 0:
            cleared_t = time.time() - t0
            break
        time.sleep(0.004)
    if cleared_t is not None:
        print(">>> %.0fms内被清零 — 设置器在运行(走别的调用点)!" % (cleared_t * 1000))
    else:
        v = u32(h, target)
        print(">>> 1s未被清(当前=%s) — 设置器没在写这个结构" % v)
        wpm(h, target, struct.pack("<i", 0))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
