# -*- coding: utf-8 -*-
"""用户物理按键标定: 节拍器引导(高音=按住D, 低音=松开), 内存同步采样差分。
注入键被游戏过滤(LL钩子查INJECTED位), 只有物理键能进 — 标定必须借用户的 手。"""
import ctypes
import sys
import time
import winsound

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

MOD_BASE = 0x400000
MOD_END = 0x8A4000
BATTLE_MGR_SOKU = 0x8985E4

CYCLES = 6
PHASE_S = 2.5          # 每相位时长
GUARD_S = 0.5          # 相位首尾丢弃(反应时间)
SAMPLE_DT = 0.10

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


def beep_hold():
    winsound.Beep(1400, 180)


def beep_release():
    winsound.Beep(700, 180)


def main(pid):
    hwnd = find_hwnd(pid)
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    sen = HudSensor(pid)

    print("请点击目标游戏窗口...")
    t0 = time.time()
    while time.time() - t0 < 60 and u32.GetForegroundWindow() != hwnd:
        time.sleep(0.2)
    if u32.GetForegroundWindow() != hwnd:
        print("!! 没等到前台")
        return
    print("焦点OK! 3秒后开始: 高音=按住D不放, 低音=松开D, 共%d轮, 跟着节奏走"
          % CYCLES)
    time.sleep(3.0)

    regions = [("module", MOD_BASE, MOD_END - MOD_BASE)]
    b = rpm(h, BATTLE_MGR_SOKU, 4)
    if b:
        mgr = int.from_bytes(b, "little")
        if 0x10000 < mgr < 0x80000000:
            regions.append(("mgr", mgr - 0x800, 0x2000))

    samples = []
    for cyc in range(CYCLES):
        for phase in (1, 0):
            (beep_hold if phase else beep_release)()
            t_start = time.time()
            t_end = t_start + PHASE_S
            while time.time() < t_end:
                t = time.time() - t_start
                in_guard = t < GUARD_S or t > PHASE_S - GUARD_S
                data = {nm: rpm(h, a, sz) for nm, a, sz in regions}
                s = sen.read()
                p1x = s["battle"]["left"]["x"] if s and s.get("battle") else None
                samples.append((phase, in_guard, data, p1x))
                time.sleep(SAMPLE_DT)
        print("  周期%d/%d完成" % (cyc + 1, CYCLES))
    winsound.Beep(1000, 400)

    # 验证用户按键生效: hold相位P1x应大于release相位(向右走)
    hx = [x for p, g, d, x in samples if p == 1 and not g and x is not None]
    ux = [x for p, g, d, x in samples if p == 0 and not g and x is not None]
    hm = sum(hx) / len(hx) if hx else 0
    um = sum(ux) / len(ux) if ux else 0
    hvar = (max(hx) - min(hx)) if hx else 0
    print("P1x: hold均值=%.0f (极差%d) release均值=%.0f → 输入%s"
          % (hm, hvar, um, "生效✓" if hm > um + 5 or hvar > 30 else "存疑!"))

    for nm, a, sz in regions:
        downs = [d[nm] for p, g, d, x in samples if p == 1 and not g and d.get(nm)]
        ups = [d[nm] for p, g, d, x in samples if p == 0 and not g and d.get(nm)]
        if len(downs) < 8 or len(ups) < 8:
            print("== %s 样本不足(%d/%d)" % (nm, len(downs), len(ups)))
            continue
        cands = []
        for off in range(min(len(downs[0]), len(ups[0]))):
            dv = [d[off] for d in downs]
            uv = [d[off] for d in ups]
            if max(dv) - min(dv) <= 2 and max(uv) - min(uv) <= 2:
                dm = sum(dv) / len(dv)
                um2 = sum(uv) / len(ups)
                if abs(dm - um2) >= 8:
                    cands.append((a + off, um2 & 0xFF, dm & 0xFF))
        print("== %s: 候选%d" % (nm, len(cands)))
        for addr, u_v, d_v in cands[:50]:
            print("   0x%08X: up=0x%02X down=0x%02X" % (addr, u_v, d_v))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
