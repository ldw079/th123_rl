# -*- coding: utf-8 -*-
"""无头 vs 渲染 对比: tps=480各60秒, 帧率+进程CPU时间。"""
import ctypes
import random
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from tm_env import TMEnv  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def cpu_time(pid):
    import ctypes.wintypes as wt
    class FT(ctypes.Structure):
        _fields_ = [("lo", wt.DWORD), ("hi", wt.DWORD)]
    class Times(ctypes.Structure):
        _fields_ = [("user", FT), ("kernel", FT)]
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    t = Times()
    ok = ctypes.windll.kernel32.GetProcessTimes(
        h, ctypes.byref(t), ctypes.byref(t), ctypes.byref(t), ctypes.byref(t))
    ctypes.windll.kernel32.CloseHandle(h)
    if not ok:
        return None
    def sec(ft):
        return ((ft.hi << 32) | ft.lo) / 1e7
    return sec(t.user) + sec(t.kernel)


def run(render, seconds=60):
    env = TMEnv(23100 if render else 23200, char_left="reimu",
                char_right="reimu", vs_com=True, tps=480, render=render)
    c0 = cpu_time(env.pid)
    t0 = time.time()
    frames = 0
    while time.time() - t0 < seconds:
        r = env.step({"H": random.choice([-1, 0, 1])}, {})
        if r is not None:
            frames += 1
    dt = time.time() - t0
    c1 = cpu_time(env.pid)
    print("render=%s: %.0f帧/s 游戏CPU=%.0f%%" % (
        render, frames / dt, 100.0 * (c1 - c0) / dt))
    env.close()
    time.sleep(1)


def main():
    run(True)
    run(False)


if __name__ == "__main__":
    main()
