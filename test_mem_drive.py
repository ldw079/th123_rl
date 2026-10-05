# -*- coding: utf-8 -*-
"""逻辑输入写入实验(用户特许训练期内存写入):
VK键态数组基址0x02F70090(差分标定), 写0x80/0x00驱动P1。
只写1字节已验证可读的槽位, 不越界。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

KB_BASE = 0x02F70090
VK_A, VK_D = 0x41, 0x44

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
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION |
                        PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print("OpenProcess(读写)失败 err=%d" % k32.GetLastError())
        return
    sen = HudSensor(pid)

    # 安检: 数组可读且当前大多为零
    arr = rpm(h, KB_BASE, 256)
    if not arr:
        print("!! 基址不可读, 放弃")
        return
    nonzero = [(i, b) for i, b in enumerate(arr) if b]
    print("数组现状: 非零槽=%s" % (nonzero[:16],))

    x0 = p1x(sen)
    print("P1x=%s, 写D=0x80 1.5秒..." % (round(x0) if x0 else None))
    if not wpm(h, KB_BASE + VK_D, b"\x80"):
        print("!! 写入失败")
        return
    time.sleep(1.5)
    wpm(h, KB_BASE + VK_D, b"\x00")
    time.sleep(0.3)
    x1 = p1x(sen)
    print("写D后 P1x=%s (Δ=%s)" % (round(x1) if x1 else None,
                                    round(x1 - x0) if x1 and x0 else None))

    print("写A=0x80 1.5秒...")
    wpm(h, KB_BASE + VK_A, b"\x80")
    time.sleep(1.5)
    wpm(h, KB_BASE + VK_A, b"\x00")
    time.sleep(0.3)
    x2 = p1x(sen)
    print("写A后 P1x=%s (Δ=%s)" % (round(x2) if x2 else None,
                                    round(x2 - x1) if x2 and x1 else None))

    ok_d = x0 is not None and x1 is not None and (x1 - x0) > 5
    ok_a = x1 is not None and x2 is not None and (x2 - x1) < -5
    if ok_d and ok_a:
        print(">>> 完美! 内存直接驱动P1成功, 双向验证通过")
    elif ok_d or ok_a:
        print(">>> 部分成功(单方向), 可能被覆盖/方向位需要伴随标志")
    else:
        arr2 = rpm(h, KB_BASE, 256)
        n2 = [(i, b) for i, b in enumerate(arr2) if b]
        print(">>> 无位移。写入后数组状态: %s (若0x44仍=0x80说明数组被游戏刷新覆盖)"
              % (n2[:16],))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
