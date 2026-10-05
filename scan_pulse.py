# -*- coding: utf-8 -*-
"""逻辑输入地址标定: 前台脉冲按D(P1右), 快照th123全局数据区, 差分相关。
自动等待焦点落到目标游戏窗口后开始。
输出: 与按键相位相关的字节偏移候选。"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import inject  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

# th123全局数据区(SwrAddr所有全局量都在0x6E4E20~0x6ECE7C)
SCAN_START = 0x6E0000
SCAN_END = 0x6F4000

VK = 0x44          # D = P1右(按config.KEYMAP)
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
    if not hwnd:
        print("找不到窗口 pid=%d" % pid)
        return
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print("OpenProcess失败")
        return
    sen = HudSensor(pid)

    print("等待前台=PID %d的窗口(请点击它)... 30s超时" % pid)
    t0 = time.time()
    while time.time() - t0 < 30:
        if u32.GetForegroundWindow() == hwnd:
            break
        time.sleep(0.2)
    else:
        print("超时: 窗口没成为前台")
        return
    print("焦点就位, 1s后开始脉冲(请不要碰键盘/鼠标)")
    time.sleep(1.0)

    size = SCAN_END - SCAN_START
    samples = []          # (phase, bytes)
    for cyc in range(CYCLES):
        for phase in (1, 0):   # 1=按下 0=松开
            if phase:
                inject.press(VK)
            else:
                inject.release(VK)
            t_end = time.time() + HOLD_S
            while time.time() < t_end:
                data = rpm(h, SCAN_START, size)
                if data:
                    samples.append((phase, data))
                time.sleep(SAMPLE_DT)
    inject.release(VK)

    ups = [d for p, d in samples if p == 0]
    downs = [d for p, d in samples if p == 1]
    print("样本: down=%d up=%d" % (len(downs), len(ups)))
    if len(downs) < 8 or len(ups) < 8:
        print("样本不足")
        return

    cands = []
    for off in range(size):
        dv = [d[off] for d in downs]
        uv = [d[off] for d in ups]
        dmin, dmax = min(dv), max(dv)
        umin, umax = min(uv), max(uv)
        # 同相稳定 + 异相分离
        if dmax - dmin <= 2 and umax - umin <= 2:
            dmean = sum(dv) / len(dv)
            umean = sum(uv) / len(uv)
            if abs(dmean - umean) >= 5:
                cands.append((SCAN_START + off, umean, dmean))

    print("候选字节 %d 个:" % len(cands))
    for addr, u_v, d_v in cands[:60]:
        print("  0x%08X: up=0x%02X down=0x%02X" % (addr, u_v & 0xFF, d_v & 0xFF))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 39208)
