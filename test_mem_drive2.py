# -*- coding: utf-8 -*-
"""逻辑输入写入实验v2: 逐候选试验(方向位0x08=右)。
候选: 0x276EFD7C, 0x276EFD7E (0x08模式, 可能是每玩家逻辑输入字节)"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400

CANDS = [0x276EFD7C, 0x276EFD7E]
VK_STATE_BASE = 0x02F70090
VK_D = 0x44

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


def p1x(sen):
    s = sen.read()
    return s["battle"]["left"]["x"] if s and s.get("battle") else None


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    sen = HudSensor(pid)

    # 先看候选地址周边结构
    ctx = rpm(h, 0x276EFD60, 0x50)
    if ctx:
        print("上下文0x276EFD60: %s" % ctx.hex())

    for addr in CANDS:
        cur = rpm(h, addr, 1)
        x0 = p1x(sen)
        print("\n== 0x%08X (当前=0x%s) P1x=%s: 写0x08按住1.5s..."
              % (addr, cur.hex() if cur else "??", round(x0) if x0 else None))
        wpm(h, addr, b"\x08")
        time.sleep(1.5)
        x1 = p1x(sen)
        wpm(h, addr, b"\x00")
        time.sleep(0.3)
        print("   结果 P1x=%s (Δ=%s)" % (round(x1) if x1 else None,
                                         round(x1 - x0) if x1 and x0 else None))
        if x0 is not None and x1 is not None and (x1 - x0) > 5:
            print("   >>> 这个地址有效! P1向右走了!")

    # 组合: 状态数组+逻辑位同写
    addr = CANDS[0]
    x0 = p1x(sen)
    print("\n== 组合(逻辑0x08+键态0x80) 1.5s...")
    wpm(h, addr, b"\x08")
    wpm(h, VK_STATE_BASE + VK_D, b"\x80")
    time.sleep(1.5)
    x1 = p1x(sen)
    wpm(h, addr, b"\x00")
    wpm(h, VK_STATE_BASE + VK_D, b"\x00")
    print("   结果 P1x=%s (Δ=%s)" % (round(x1) if x1 else None,
                                     round(x1 - x0) if x1 and x0 else None))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
