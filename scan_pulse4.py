# -*- coding: utf-8 -*-
"""标定v4(精简): 等用户亲手点窗口获得真前台 → D自检 → 脉冲采样差分。
不SetForegroundWindow(后台抢不到), 不Esc(活的回合会被暂停)。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import inject  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

MOD_BASE = 0x400000
MOD_END = 0x8A4000
BATTLE_MGR_SOKU = 0x8985E4

VK = 0x44          # D = P1右
CYCLES = 6
HOLD_S = 1.5
SAMPLE_DT = 0.12

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


def rpm(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                 buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main(pid):
    hwnd = find_hwnd(pid)
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    sen = HudSensor(pid)

    print("请点击目标游戏窗口(保持前台)... 60s")
    t0 = time.time()
    while time.time() - t0 < 60 and u32.GetForegroundWindow() != hwnd:
        time.sleep(0.2)
    if u32.GetForegroundWindow() != hwnd:
        print("!! 没等到前台")
        return
    print("焦点OK(用户点击), 自检D...")

    def p1x():
        s = sen.read()
        return s["battle"]["left"]["x"] if s and s.get("battle") else None

    ok = False
    for i in range(5):
        x0 = p1x()
        inject.press(VK)
        time.sleep(1.0)
        inject.release(VK)
        x1 = p1x()
        print("自检#%d D: P1x %s→%s (焦点=%s)"
              % (i, round(x0) if x0 else None, round(x1) if x1 else None,
                 u32.GetForegroundWindow() == hwnd))
        if x0 is not None and x1 is not None and abs(x1 - x0) >= 2:
            ok = True
            break
        time.sleep(1.0)
    if not ok:
        print("!! D驱动失败(输入仍未进游戏), 退出")
        return

    regions = [("module", MOD_BASE, MOD_END - MOD_BASE)]
    b = rpm(h, BATTLE_MGR_SOKU, 4)
    if b:
        mgr = int.from_bytes(b, "little")
        if 0x10000 < mgr < 0x80000000:
            regions.append(("mgr", mgr - 0x800, 0x2000))
    samples = []
    print("采样中(%d周期, 保持前台别动)... " % CYCLES)
    for cyc in range(CYCLES):
        for phase in (1, 0):
            if phase:
                inject.press(VK)
            else:
                inject.release(VK)
            t_end = time.time() + HOLD_S
            while time.time() < t_end:
                data = {nm: rpm(h, a, sz) for nm, a, sz in regions}
                samples.append((phase, data, p1x()))
                time.sleep(SAMPLE_DT)
    inject.release(VK)

    for nm, a, sz in regions:
        downs = [d[nm] for p, d, x in samples if p == 1 and d.get(nm)]
        ups = [d[nm] for p, d, x in samples if p == 0 and d.get(nm)]
        if len(downs) < 8 or len(ups) < 8:
            continue
        cands = []
        for off in range(min(len(downs[0]), len(ups[0]))):
            dv = [d[off] for d in downs]
            uv = [d[off] for d in ups]
            if max(dv) - min(dv) <= 2 and max(uv) - min(uv) <= 2:
                dm = sum(dv) / len(dv)
                um = sum(uv) / len(ups)
                if abs(dm - um) >= 8:
                    cands.append((a + off, um & 0xFF, dm & 0xFF))
        print("== %s: 候选%d" % (nm, len(cands)))
        for addr, u_v, d_v in cands[:50]:
            print("   0x%08X: up=0x%02X down=0x%02X" % (addr, u_v, d_v))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
