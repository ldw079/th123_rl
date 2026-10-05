# -*- coding: utf-8 -*-
"""逻辑输入地址标定v3: 逐级验证(焦点→帧→P1被驱动)后差分。
任何一级失败都会明确报告, 不出垃圾结果。"""
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
PBATTLEMGR = 0x6E6244

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


def frame_of(sen):
    s = sen.read()
    return s["battle"]["frame"] if s and s.get("battle") else None


def main(pid):
    hwnd = find_hwnd(pid)
    if not hwnd:
        print("找不到窗口")
        return
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    sen = HudSensor(pid)

    # ① 焦点: 先自己试, 不行请用户点
    u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    time.sleep(0.5)
    if u32.GetForegroundWindow() != hwnd:
        print("自动取焦点失败 — 请点击目标游戏窗口(15s等待)")
        t0 = time.time()
        while time.time() - t0 < 15 and u32.GetForegroundWindow() != hwnd:
            time.sleep(0.2)
    if u32.GetForegroundWindow() != hwnd:
        print("!! 没拿到焦点, 退出")
        return
    print("①焦点OK")

    # ② 解暂停: 失焦自动暂停只冻结模拟不冻结帧计数, 必须用HP/位移判活
    def live_probe():
        s1 = sen.read()
        a = (s1["battle"]["left"]["x"], s1["battle"]["right"]["x"],
             s1["battle"]["left"]["hp"]) if s1 and s1.get("battle") else None
        time.sleep(1.2)
        s2 = sen.read()
        b = (s2["battle"]["left"]["x"], s2["battle"]["right"]["x"],
             s2["battle"]["left"]["hp"]) if s2 and s2.get("battle") else None
        if not a or not b:
            return False
        return (abs(a[0] - b[0]) > 1 or abs(a[1] - b[1]) > 1 or a[2] != b[2])

    for attempt in range(4):
        if live_probe():
            print("②对局活着(位置/HP在变)")
            break
        print("②对局冻结(暂停?), 按Esc...")
        inject.tap(0x1B, 0.12)
        time.sleep(0.9)
        s = sen.read()
        if s and s.get("scene") != 5:
            print("!! Esc后离开对局场景(scene=%s), 退出保安全" % s.get("scene"))
            return
    else:
        print("!! 4轮Esc后仍无生命迹象, 退出")
        return

    # ③ 输入自检: 多键×多轮重试(避开回合切换/硬直等瞬时不可控状态)
    ok = False
    for attempt in range(4):
        s = sen.read()
        if s and s.get("battle"):
            b = s["battle"]
            print("  状态: scene=%s round=%s match=%s HP(L/R)=%s/%s P1x=%s"
                  % (s.get("scene"), b.get("round"), b.get("match_state"),
                     b["left"].get("hp"), b["right"].get("hp"),
                     round(b["left"]["x"])))
        x0 = s["battle"]["left"]["x"] if s and s.get("battle") else None
        vk_try = (VK, 0x41) if attempt % 2 == 0 else (0x41, VK)  # D右/A左交替
        inject.press(vk_try[0])
        time.sleep(1.0)
        inject.release(vk_try[0])
        s = sen.read()
        x1 = s["battle"]["left"]["x"] if s and s.get("battle") else None
        print("③自检#%d key=%s: P1x %s→%s" % (attempt, chr(vk_try[0]),
                                              round(x0) if x0 else None,
                                              round(x1) if x1 else None))
        if x0 is not None and x1 is not None and abs(x1 - x0) >= 2:
            ok = True
            break
        time.sleep(2.0)
    if not ok:
        print("!! 4轮自检P1都没动 — P1可能不是人类槽(COM)或被压制, 退出")
        return

    # ④ 正式差分
    regions = [("module", MOD_BASE, MOD_END - MOD_BASE)]
    b = rpm(h, PBATTLEMGR, 4)
    if b:
        mgr = int.from_bytes(b, "little")
        if 0x10000 < mgr < 0x7FFFFFFF:
            regions.append(("mgr", mgr - 0x800, 0x2000))
    samples = []
    print("④脉冲采样中(%d周期)..." % CYCLES)
    time.sleep(0.8)
    for cyc in range(CYCLES):
        for phase in (1, 0):
            if phase:
                inject.press(VK)
            else:
                inject.release(VK)
            t_end = time.time() + HOLD_S
            while time.time() < t_end:
                data = {nm: rpm(h, a, sz) for nm, a, sz in regions}
                s = sen.read()
                p1x = s["battle"]["left"]["x"] if s and s.get("battle") else None
                samples.append((phase, data, p1x))
                time.sleep(SAMPLE_DT)
    inject.release(VK)

    for nm, a, sz in regions:
        downs = [d[nm] for p, d, x in samples if p == 1 and d.get(nm)]
        ups = [d[nm] for p, d, x in samples if p == 0 and d.get(nm)]
        if len(downs) < 8 or len(ups) < 8:
            print("== %s 样本不足" % nm)
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
        for addr, u_v, d_v in cands[:40]:
            print("   0x%08X: up=0x%02X down=0x%02X" % (addr, u_v, d_v))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 39208)
