# -*- coding: utf-8 -*-
"""逻辑输入地址标定v2:
- SetForegroundWindow接管(标定特许) + Esc解暂停
- 全模块扫描(0x400000-0x8A4000) + PBATTLEMGR堆对象 ±0x800 + 双方角色对象
- 每样本记录P1x(验证输入真的驱动了游戏)
- 相关判据: 同相稳定(极差<=2) 跨相分离(>=8)"""
import ctypes
import ctypes.wintypes as wt
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
PBATTLEMGR = 0x6E6244
LCHAR_OFS = 0x0C
RCHAR_OFS = 0x10

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


def u32le(b, off=0):
    return int.from_bytes(b[off:off + 4], "little")


def main(pid):
    hwnd = find_hwnd(pid)
    if not hwnd:
        print("找不到窗口")
        return
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print("OpenProcess失败")
        return
    sen = HudSensor(pid)

    print("接管焦点...")
    u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    time.sleep(0.8)
    # Esc解暂停(若没暂停则可能进暂停 — 先看frame是否在动)
    s = sen.read()
    f1 = s["battle"]["frame"] if s and s.get("battle") else None
    time.sleep(0.5)
    s = sen.read()
    f2 = s["battle"]["frame"] if s and s.get("battle") else None
    print("frame: %s → %s" % (f1, f2))
    if f1 is not None and f2 is not None and f2 == f1:
        print("帧静止(暂停?), 按Esc解暂停")
        inject.tap(0x1B, 0.12)
        time.sleep(0.6)
        s = sen.read()
        f3 = s["battle"]["frame"] if s and s.get("battle") else None
        print("Esc后frame: %s → %s" % (f2, f3))

    # 扫描区域收集
    regions = [("module", MOD_BASE, MOD_END - MOD_BASE)]
    b = rpm(h, PBATTLEMGR, 4)
    if b:
        mgr = u32le(b)
        if 0x10000 < mgr < 0x7FFFFFFF:
            regions.append(("mgr", mgr - 0x800, 0x1800))
            mb = rpm(h, mgr, 0x20)
            if mb:
                for nm, ofs in (("Lchar", LCHAR_OFS), ("Rchar", RCHAR_OFS)):
                    p = u32le(mb, ofs)
                    if 0x10000 < p < 0x7FFFFFFF:
                        regions.append((nm, p - 0x100, 0xB00))
    for nm, a, sz in regions:
        print("扫描区 %s: 0x%X +0x%X" % (nm, a, sz))

    # 基线有效性
    snaps = [(nm, a, sz, rpm(h, a, sz)) for nm, a, sz in regions]
    regions = [(nm, a, sz) for nm, a, sz, v in snaps if v]
    if not regions:
        print("全失败")
        return

    samples = []   # (phase, {name: bytes}, p1x)
    print("开始脉冲(D)... 请不要碰键鼠")
    time.sleep(0.8)
    for cyc in range(CYCLES):
        for phase in (1, 0):
            if phase:
                inject.press(VK)
            else:
                inject.release(VK)
            t_end = time.time() + HOLD_S
            while time.time() < t_end:
                data = {}
                for nm, a, sz in regions:
                    data[nm] = rpm(h, a, sz)
                s = sen.read()
                p1x = s["battle"]["left"]["x"] if s and s.get("battle") else None
                samples.append((phase, data, p1x))
                time.sleep(SAMPLE_DT)
    inject.release(VK)

    # 验证输入有效: down相位P1x应变化
    downs_x = [x for p, d, x in samples if p == 1]
    ups_x = [x for p, d, x in samples if p == 0]
    dxs = [x for x in downs_x if x is not None]
    moved = len(dxs) > 2 and max(dxs) - min(dxs) > 2
    print("down相位P1x样本: %s | 移动=%s" % ([round(x) for x in downs_x[:8]], moved))
    if not moved:
        print("!! D键没有驱动P1 — 输入未生效, 标定无效")

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
                um = sum(uv) / len(uv)
                if abs(dm - um) >= 8:
                    cands.append((a + off, um & 0xFF, dm & 0xFF))
        print("== %s: 候选%d" % (nm, len(cands)))
        for addr, u_v, d_v in cands[:40]:
            print("   0x%08X: up=0x%02X down=0x%02X" % (addr, u_v, d_v))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 39208)
