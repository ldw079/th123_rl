# -*- coding: utf-8 -*-
"""验证mod重定向是否真的写入: 启动训练游戏→握手后读0x40A45D字节。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client import SokuInstance  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

k32 = ctypes.windll.kernel32


def main():
    inst = SokuInstance(20763)
    pid = inst.proc.pid
    print("PID=%d" % pid)
    h = k32.OpenProcess(0x0410, False, pid)
    b = ctypes.create_string_buffer(8)
    g = ctypes.c_size_t()
    k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(0x40A45D), b, 8,
                          ctypes.byref(g))
    print("0x40A45D字节: %s" % b.raw[:8].hex())
    if b.raw[0] == 0xE8:
        operand = struct.unpack("<i", b.raw[1:5])[0]
        target = 0x40A462 + operand
        print("call目标=0x%X %s" % (target,
              "(我们的mod区!)" if 0x60000000 < target < 0x80000000 else
              "(sub_40A1A0=0x40A1A0 未重定向!)" if target == 0x40A1A0 else "(其它)"))
    time.sleep(1)
    inst.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
