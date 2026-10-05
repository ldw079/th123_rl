# -*- coding: utf-8 -*-
"""VS_PLAYER停摆后验尸: 进程存活/场景归宿/新crash dump/连接状态。"""
import ctypes
import os
import random
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client2 import (SokuTrainerInstance, CHAR_REIMU, GameEnded,
                          OPCODE_VS_PLAYER_START_GAME)  # noqa: E402

k32 = ctypes.windll.kernel32
SCENE = 0x8A0044
CRASH_DIR = r"D:\touhou\hisoutensoku2026-06-15\th123_train\crashes"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def crashes_before():
    return {f: os.path.getmtime(os.path.join(CRASH_DIR, f))
            for f in os.listdir(CRASH_DIR)}


def ri():
    return {"H": random.choice([-1, 0, 1]), "A": random.random() < 0.15}


def main():
    c0 = crashes_before()
    inst = SokuTrainerInstance(24002)
    pid = inst.proc.pid
    h = k32.OpenProcess(0x0410, False, pid)
    print("PID=%d" % pid)
    deck = list(range(1, 21))
    pkt = struct.pack("<BBBI20sB32sI20sB32s",
                      OPCODE_VS_PLAYER_START_GAME, 0, 0,
                      CHAR_REIMU, bytes(deck), 0, b"RL-L".ljust(32, b"\0"),
                      CHAR_REIMU, bytes(deck), 0, b"RL-R".ljust(32, b"\0"))
    inst._send(pkt)
    r = inst._recv_exact(1, 15.0)[0]
    print("开局 op=%s" % r)
    if r != 12:
        return

    frames = 0
    last_scene = None
    t0 = time.time()
    stalled_at = None
    while time.time() - t0 < 40:
        b = ctypes.create_string_buffer(1)
        g = ctypes.c_size_t()
        if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                 b, 1, ctypes.byref(g)):
            if b.raw[0] != last_scene:
                print("[%4.1fs] scene=%s" % (time.time() - t0, b.raw[0]))
                last_scene = b.raw[0]
        inst.send_inputs(ri(), ri())
        try:
            left, right, weather, objs = inst.recv_frame(timeout=3.0)
        except (RuntimeError, GameEnded) as e:
            if "err=17" in str(e) or "err=12" in str(e):
                continue
            print("终止@%d: %s" % (frames, e))
            break
        except Exception as e:
            print("终止@%d: %s: %s" % (frames, type(e).__name__, e))
            stalled_at = time.time()
            break
        frames += 1

    # ---- 验尸 ----
    print("\n--- 验尸(停摆后10s) ---")
    time.sleep(10)
    code = ctypes.c_ulong()
    ph = k32.OpenProcess(0x1000, False, pid)  # PROCESS_TERMINATE只查询不行, 用退出码
    ph = k32.OpenProcess(0x0400 | 0x0010, False, pid)
    alive = bool(ph)
    if ph:
        k32.GetExitCodeProcess(ph, ctypes.byref(code))
        k32.CloseHandle(ph)
    print("进程句柄=%s 退出码=%s(%s)" % (
        alive, code.value, "仍在运行" if code.value == 259 else "已退出"))
    b = ctypes.create_string_buffer(1)
    g = ctypes.c_size_t()
    if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                             b, 1, ctypes.byref(g)):
        print("终态scene=%s" % b.raw[0])
    new_dumps = {f: m for f, m in crashes_before().items()
                 if f not in c0 or c0[f] != m}
    print("新crash dump: %s" % (list(new_dumps) or "无"))
    inst.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
