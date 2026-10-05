# -*- coding: utf-8 -*-
"""VS_PLAYER重测(协议五bug修复后): 独立实例24000端口, 双方随机输入,
看能否出帧/掉血/完赛。规范§8: 实验不占训练端口。"""
import random
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client2 import (SokuTrainerInstance, CHAR_REIMU, GameEnded,
                          OPCODE_VS_PLAYER_START_GAME)  # noqa: E402
import struct  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ri():
    return {"H": random.choice([-1, 0, 1]), "A": random.random() < 0.15,
            "B": random.random() < 0.15, "C": random.random() < 0.03}


def main():
    inst = SokuTrainerInstance(24000)
    print("PID=%s 握手OK" % inst.proc.pid)
    deck = list(range(1, 21))
    pkt = struct.pack("<BBBI20sB32sI20sB32s",
                      OPCODE_VS_PLAYER_START_GAME, 0, 0,
                      CHAR_REIMU, bytes(deck), 0, b"RL-L".ljust(32, b"\0"),
                      CHAR_REIMU, bytes(deck), 0, b"RL-R".ljust(32, b"\0"))
    inst._send(pkt)
    r = inst._recv_exact(1, 15.0)[0]
    print("开局应答 op=%s" % r)
    if r != 12:
        if r == 7:
            print("err=%d" % inst._recv_exact(1)[0])
        return

    frames = 0
    t0 = time.time()
    while time.time() - t0 < 90:
        inst.send_inputs(ri(), ri())
        try:
            left, right, weather, objs = inst.recv_frame(timeout=30.0 if frames == 0 else 3.0)
        except GameEnded as ge:
            print("完赛@%d帧: %s" % (frames, ge))
            break
        except Exception as e:
            print("终止@%d帧: %s: %s" % (frames, type(e).__name__, e))
            break
        frames += 1
        if frames % 300 == 0:
            print("帧%d: L.hp=%s x=%.0f R.hp=%s x=%.0f obj=%d" % (
                frames, left["hp"], left["position.x"], right["hp"],
                right["position.x"], len(objs)))
    print("共%d帧" % frames)
    inst.close()


if __name__ == "__main__":
    main()
