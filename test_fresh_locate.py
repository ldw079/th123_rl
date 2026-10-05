# -*- coding: utf-8 -*-
"""闭环实验: 用户按D期间实时定位候选地址的现行值 → 松开后立即写入测试。
解决: 堆地址过期 / 回合非活 / 写入目标错误 三个疑点一次判明。"""
import ctypes
import sys
import time
import winsound

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400

OLD_CANDS = [0x02F700D4, 0x276EFD7C, 0x276EFD7E, 0x0CD6FC98]
VK_BASE_OLD = 0x02F70090

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_hwnd(pid):
    from capture import find_windows
    for hwnd, title in find_windows("非想天"):
        p = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            return hwnd
    return None


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
    hwnd = find_hwnd(pid)

    print("等待点击目标窗口...")
    t0 = time.time()
    while time.time() - t0 < 60 and u32.GetForegroundWindow() != hwnd:
        time.sleep(0.2)
    if u32.GetForegroundWindow() != hwnd:
        print("没等到焦点")
        return

    # ① 高音→按住D 2.5秒 (实时采样候选+P1x)
    print("焦点OK, 1秒后高音=按住D 2.5秒")
    time.sleep(1.0)
    winsound.Beep(1400, 250)
    hold_vals = {a: [] for a in OLD_CANDS}
    xs = []
    t_end = time.time() + 2.5
    while time.time() < t_end:
        for a in OLD_CANDS:
            v = rpm(h, a, 1)
            if v:
                hold_vals[a].append(v[0])
        xs.append(p1x(sen))
        time.sleep(0.05)
    winsound.Beep(700, 250)   # 松开
    print("hold P1x: %s" % [round(x) for x in xs if x is not None])
    moved = xs and max(xs) - min(xs) > 5
    print("用户按D驱动P1: %s" % ("是, 回合活" if moved else "否! 回活不可用或输入没进"))

    # ② 松开状态采样
    time.sleep(0.8)
    rel_vals = {a: [] for a in OLD_CANDS}
    t_end = time.time() + 2.0
    while time.time() < t_end:
        for a in OLD_CANDS:
            v = rpm(h, a, 1)
            if v:
                rel_vals[a].append(v[0])
        time.sleep(0.05)

    for a in OLD_CANDS:
        hv, rv = hold_vals[a], rel_vals[a]
        if not hv or not rv:
            print("0x%08X: 读取失败(地址失效!)" % a)
            continue
        hs = sorted(set(hv))
        rs = sorted(set(rv))
        print("0x%08X: hold=%s release=%s" % (a,
              ["0x%02X" % v for v in hs[:6]], ["0x%02X" % v for v in rs[:6]]))

    if not moved:
        print("!! 回合不活/输入没进 — 写入测试无意义, 先解决状态")
        k32.CloseHandle(ctypes.c_void_p(h))
        return

    # ③ 写入测试(60Hz重写): 对hold期间变为0x80/0x08的地址
    print("\n写入测试(每候选120Hz重写1.5s)...")
    for a in OLD_CANDS:
        hv = hold_vals[a]
        if not hv:
            continue
        target = max(set(hv), key=hv.count)
        if target in (0,):
            continue
        x0 = p1x(sen)
        t_end = time.time() + 1.5
        while time.time() < t_end:
            wpm(h, a, bytes([target]))
            time.sleep(1.0 / 120)
        wpm(h, a, b"\x00")
        time.sleep(0.3)
        x1 = p1x(sen)
        d = (x1 - x0) if (x1 is not None and x0 is not None) else None
        print("  0x%08X=0x%02X: Δ=%s%s" % (a, target, round(d) if d is not None else None,
              "  <<< 有效!!" if d and d > 5 else ""))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
