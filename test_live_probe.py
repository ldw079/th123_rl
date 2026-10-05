# -*- coding: utf-8 -*-
"""活性探针+活窗写入: 写0x08后5ms级回读, 检测引擎清零(=活).
活窗出现立即120Hz泵1.5s测位移。90s无活窗则报告。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
TARGET = 0x276EFD7C

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rpm1(h, addr):
    buf = ctypes.create_string_buffer(1)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                 buf, 1, ctypes.byref(got)) or got.value != 1:
        return None
    return buf.raw[0]


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
    print("探测引擎活性(最多90s)...")
    t0 = time.time()
    cleared = 0
    stuck = 0
    while time.time() - t0 < 90:
        wpm(h, TARGET, b"\x08")
        t_clear = time.time()
        seen_clear = False
        while time.time() - t_clear < 0.25:
            v = rpm1(h, TARGET)
            if v is not None and v != 0x08:
                if v == 0:
                    seen_clear = True
                    break
                else:
                    # 被写成别的值(比如0x0A其他键), 也算引擎活动
                    seen_clear = True
                    break
            time.sleep(0.005)
        if seen_clear:
            cleared += 1
        else:
            stuck += 1
            wpm(h, TARGET, b"\x00")
        if cleared >= 3:
            break
        time.sleep(0.3)
    print("探测结果: 清零%d次 / 驻留%d次" % (cleared, stuck))
    if cleared < 3:
        print("!! 引擎不清零该字节 — 或地址错或无活窗(对局结束?). 需要人工重开对局")
        return

    # 活窗确认 → 泵测试
    print("活窗! 泵0x08 1.5s...")
    x0 = p1x(sen)
    t_end = time.time() + 1.5
    n = 0
    while time.time() < t_end:
        wpm(h, TARGET, b"\x08")
        n += 1
        time.sleep(1.0 / 120)
    wpm(h, TARGET, b"\x00")
    time.sleep(0.3)
    x1 = p1x(sen)
    d = (x1 - x0) if (x1 is not None and x0 is not None) else None
    print("泵%d次 P1x %s→%s Δ=%s %s" % (n, round(x0) if x0 else None,
          round(x1) if x1 else None, round(d) if d is not None else None,
          "<<< 成功!!!" if d and d > 5 else "(无效)"))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
