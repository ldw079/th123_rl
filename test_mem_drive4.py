# -*- coding: utf-8 -*-
"""写入测试v4: 明确对 0x276EFD7C/7E 以120Hz泵入0x08, 同时监测字节是否驻留。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rpm(h, addr, n=1):
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
    if not h:
        print("OpenProcess失败")
        return
    sen = HudSensor(pid)

    for name, addrs in [("7C单独", [0x276EFD7C]),
                        ("7E单独", [0x276EFD7E]),
                        ("7C+7E", [0x276EFD7C, 0x276EFD7E])]:
        x0 = p1x(sen)
        seen = []
        t_end = time.time() + 1.5
        n = 0
        while time.time() < t_end:
            for a in addrs:
                wpm(h, a, b"\x08")
            n += 1
            if n % 12 == 0:
                v = rpm(h, addrs[0])
                if v:
                    seen.append(v[0])
            time.sleep(1.0 / 120)
        for a in addrs:
            wpm(h, a, b"\x00")
        time.sleep(0.3)
        x1 = p1x(sen)
        d = (x1 - x0) if (x1 is not None and x0 is not None) else None
        print("%-8s 泵%d次 字节观测=%s P1x %s→%s Δ=%s%s"
              % (name, n, ["0x%02X" % v for v in seen[:8]],
                 round(x0) if x0 else None, round(x1) if x1 else None,
                 round(d) if d is not None else None,
                 "  <<< 有效!!!" if d and d > 5 else ""))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
