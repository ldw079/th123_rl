# -*- coding: utf-8 -*-
"""逻辑输入写入实验v3: 60Hz持续重写(对抗每帧消费清零)。
逐候选: 0x276EFD7C/7E(方向位0x08), 0x0CD6FC98(键态0x80), 组合。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400

VK_STATE_BASE = 0x02F70090
VK_D = 0x44

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def wpm(h, addr, data):
    got = ctypes.c_size_t()
    return bool(k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                       data, len(data), ctypes.byref(got)))


def p1x(sen):
    s = sen.read()
    return s["battle"]["left"]["x"] if s and s.get("battle") else None


def pump(h, addr, val, seconds, hz=120):
    t_end = time.time() + seconds
    n = 0
    while time.time() < t_end:
        wpm(h, addr, bytes([val]))
        n += 1
        time.sleep(1.0 / hz)
    return n


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    if not h:
        print("OpenProcess失败")
        return
    sen = HudSensor(pid)

    for name, addr, val in [
        ("逻辑位0x276EFD7C=0x08", 0x276EFD7C, 0x08),
        ("逻辑位0x276EFD7E=0x08", 0x276EFD7E, 0x08),
        ("键态0x0CD6FC98=0x80", 0x0CD6FC98, 0x80),
        ("组合: 逻辑7C+键态数组D", 0x276EFD7C, 0x08),
    ]:
        x0 = p1x(sen)
        if "组合" in name:
            n = 0
            t_end = time.time() + 1.5
            while time.time() < t_end:
                wpm(h, 0x276EFD7C, b"\x08")
                wpm(h, 0x276EFD7E, b"\x08")
                wpm(h, VK_STATE_BASE + VK_D, b"\x80")
                n += 1
                time.sleep(1.0 / 120)
        else:
            n = pump(h, addr, val, 1.5)
        x1 = p1x(sen)
        # 全部清零
        wpm(h, 0x276EFD7C, b"\x00")
        wpm(h, 0x276EFD7E, b"\x00")
        wpm(h, VK_STATE_BASE + VK_D, b"\x00")
        wpm(h, 0x0CD6FC98, b"\x00")
        time.sleep(0.3)
        d = (x1 - x0) if (x1 is not None and x0 is not None) else None
        print("%-24s P1x %s→%s Δ=%s %s" % (name, round(x0) if x0 else None,
                                            round(x1) if x1 else None,
                                            round(d) if d is not None else None,
                                            " <<< 有效!" if d and d > 5 else ""))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
