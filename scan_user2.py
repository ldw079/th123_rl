# -*- coding: utf-8 -*-
"""全堆两阶段标定:
阶段A: 用户按住D 4秒 → 全堆快照对比找'热页'(期间有写入的4KB页)
阶段B: 节拍器6轮 → 只对热页做相位相关(稳定+分离)
数据都留着, 事后可做环形缓冲分析。"""
import ctypes
import ctypes.wintypes as wt
import sys
import time
import winsound

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_INFORMATION_EX = 0x1000

MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
MEM_PRIVATE = 0x20000

CYCLES = 6
PHASE_S = 2.5
GUARD_S = 0.5
SAMPLE_DT = 0.10
MAX_HOT_BYTES = 24 * 1024 * 1024

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


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


def rw_regions(h):
    """全部已提交可写私有区(堆/数据)。"""
    out = []
    addr = 0
    mbi = MBI()
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                  ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        size = mbi.RegionSize or 0x1000
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and \
           mbi.Protect in (PAGE_READWRITE, PAGE_WRITECOPY) and size >= 0x1000:
            out.append((mbi.BaseAddress or addr, size))
        addr = (mbi.BaseAddress or addr) + size
    return out


def beep_dir(key):
    """2短鸣=D(右), 3短鸣=A(左) — 蜂鸣数报方向, 防角色顶板边。"""
    for _ in range(2 if key == "D" else 3):
        winsound.Beep(1400, 120)
        time.sleep(0.08)


def pick_dir(p1x):
    return "A" if (p1x or 590) > 590 else "D"


def main(pid):
    hwnd = find_hwnd(pid)
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    sen = HudSensor(pid)

    regions = rw_regions(h)
    total = sum(s for _, s in regions)
    print("可写私有区 %d 个, 共 %.1fMB" % (len(regions), total / 1048576.0))

    print("请点击目标游戏窗口...")
    t0 = time.time()
    while time.time() - t0 < 60 and u32.GetForegroundWindow() != hwnd:
        time.sleep(0.2)
    if u32.GetForegroundWindow() != hwnd:
        print("!! 没等到前台")
        return

    # ---- 阶段A: 按住方向键找热页(2鸣=D, 3鸣=A, 防顶墙) ----
    s0 = sen.read()
    p1x0 = s0["battle"]["left"]["x"] if s0 and s0.get("battle") else None
    key_a = pick_dir(p1x0)
    print("焦点OK。%s = 按住%s键4秒(低音后松开)..." %
          ("两声短鸣" if key_a == "D" else "三声短鸣", key_a))
    time.sleep(1.5)
    beep_dir(key_a)
    base_snaps = []
    t_end = time.time() + 4.0
    hold_snaps = []
    ax = []
    while time.time() < t_end:
        hold_snaps.append({a: rpm(h, a, s) for a, s in regions})
        s0 = sen.read()
        if s0 and s0.get("battle"):
            ax.append(s0["battle"]["left"]["x"])
        time.sleep(0.25)
    winsound.Beep(700, 300)
    arange = (max(ax) - min(ax)) if ax else 0
    print("阶段A P1x极差=%s (key=%s)" % (round(arange, 1), key_a))
    if arange < 5:
        print("!! 阶段A按键没驱动P1 — 中止")
        winsound.Beep(300, 800)
        k32.CloseHandle(ctypes.c_void_p(h))
        return
    # 松开后再采一组(基线: 空闲时的自然变化)
    time.sleep(1.0)
    t_end = time.time() + 3.0
    while time.time() < t_end:
        base_snaps.append({a: rpm(h, a, s) for a, s in regions})
        time.sleep(0.25)

    hot_pages = []   # (addr, size) 收缩到4KB粒度
    for a, s in regions:
        h0 = hold_snaps[0].get(a)
        hN = hold_snaps[-1].get(a)
        if not h0 or not hN or len(h0) != len(hN):
            continue
        # 找变化的4KB块
        for off in range(0, len(h0) - 4096 + 1, 4096):
            b0 = h0[off:off + 4096]
            bN = hN[off:off + 4096]
            if b0 != bN:
                # 再验证: 松开基线期间该块是否也在变(纯噪声块照收, 后面相位判别)
                hot_pages.append((a + off, 4096))
    hot_bytes = sum(s for _, s in hot_pages)
    print("热页 %d 个, 共 %.1fMB" % (len(hot_pages), hot_bytes / 1048576.0))
    if hot_bytes > MAX_HOT_BYTES:
        # 太大就按页内变化字节数排序砍掉尾巴 — 简化: 保留全部但警告
        print("!! 热区过大, 相关分析可能较慢")

    # ---- 阶段B: 节拍器相位相关(只采热页) ----
    print("3秒后开始节拍器(每相位开头: 2鸣=按住D, 3鸣=按住A, 低音=松开)...")
    time.sleep(3.0)
    samples = []
    first_key = "A" if key_a == "D" else "D"   # 阶段A已把角色带向一侧, 反向开始
    for cyc in range(CYCLES):
        key = first_key if cyc % 2 == 0 else ("D" if first_key == "A" else "A")
        for phase in (1, 0):
            if phase:
                beep_dir(key)
            else:
                winsound.Beep(700, 180)
            t_start = time.time()
            t_end = t_start + PHASE_S
            while time.time() < t_end:
                t = time.time() - t_start
                in_guard = t < GUARD_S or t > PHASE_S - GUARD_S
                data = {a: rpm(h, a, s) for a, s in hot_pages}
                s2 = sen.read()
                p1x = s2["battle"]["left"]["x"] if s2 and s2.get("battle") else None
                samples.append((key, phase, in_guard, data, p1x))
                time.sleep(SAMPLE_DT)
        print("  周期%d/%d (key=%s)" % (cyc + 1, CYCLES, key))
    winsound.Beep(1000, 400)

    hx = [x for k, p, g, d, x in samples if p == 1 and not g and x is not None]
    ux = [x for k, p, g, d, x in samples if p == 0 and not g and x is not None]
    print("P1x hold极差=%s release极差=%s"
          % (max(hx) - min(hx) if hx else None, max(ux) - min(ux) if ux else None))

    for key in ("D", "A"):
        downs = [d for k, p, g, d, x in samples if k == key and p == 1 and not g]
        ups = [d for k, p, g, d, x in samples if k == key and p == 0 and not g]
        n = len(downs)
        m = len(ups)
        if n < 6 or m < 6:
            print("== key=%s 样本不足(%d/%d)" % (key, n, m))
            continue
        cands = []
        for a, sz in hot_pages:
            dvs = [d[a] for d in downs if a in d and d[a] is not None]
            uvs = [u[a] for u in ups if a in u and u[a] is not None]
            if len(dvs) < 6 or len(uvs) < 6:
                continue
            if len({len(v) for v in dvs}) != 1:
                continue
            for off in range(sz):
                dv = [v[off] for v in dvs]
                uv = [v[off] for v in uvs]
                if max(dv) - min(dv) <= 2 and max(uv) - min(uv) <= 2:
                    dm = sum(dv) / len(dv)
                    um2 = sum(uv) / len(uv)
                    if abs(dm - um2) >= 8:
                        cands.append((a + off, int(um2) & 0xFF, int(dm) & 0xFF))
        print("== key=%s: 候选%d" % (key, len(cands)))
        for addr, u_v, d_v in cands[:60]:
            print("   0x%08X: up=0x%02X down=0x%02X" % (addr, u_v, d_v))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
