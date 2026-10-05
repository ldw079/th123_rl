# -*- coding: utf-8 -*-
"""VS_PLAYER深度诊断: 场景轨迹+err容忍循环, 定位卡点(loading?title回弹?)。"""
import ctypes
import random
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client2 import (SokuTrainerInstance, CHAR_REIMU, GameEnded,
                          OPCODE_VS_PLAYER_START_GAME)  # noqa: E402

k32 = ctypes.windll.kernel32
SCENE = 0x8A0044

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ri():
    return {"H": random.choice([-1, 0, 1]), "A": random.random() < 0.15}


def main():
    inst = SokuTrainerInstance(24001)
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
    print("开局应答 op=%s" % r)
    if r != 12:
        return

    frames = 0
    last_scene = None
    t0 = time.time()
    while time.time() - t0 < 60:
        b = ctypes.create_string_buffer(1)
        g = ctypes.c_size_t()
        if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                 b, 1, ctypes.byref(g)):
            if b.raw[0] != last_scene:
                print("[%4.1fs] scene=%s" % (time.time() - t0, b.raw[0]))
                last_scene = b.raw[0]
        inst.send_inputs(ri(), ri())
        try:
            left, right, weather, objs = inst.recv_frame(timeout=2.0)
        except GameEnded as ge:
            print("完赛@%d: %s" % (frames, ge))
            break
        except RuntimeError as e:
            if "err=17" in str(e) or "err=12" in str(e):
                continue    # 未进战斗 — 继续喂(锁步纪律)
            print("终止@%d: %s" % (frames, e))
            break
        except Exception as e:
            print("终止@%d: %s: %s" % (frames, type(e).__name__, e))
            break
        frames += 1
        if frames % 300 == 0:
            print("帧%d: L.hp=%s R.hp=%s obj=%d" % (
                frames, left["hp"], right["hp"], len(objs)))
    print("共%d帧" % frames)
    inst.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
