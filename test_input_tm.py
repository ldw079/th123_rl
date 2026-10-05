# -*- coding: utf-8 -*-
"""输入落地干净对照: TM实例 → 前240帧无输入(基线) → H=+1连续180帧 → H=-1连续120帧。
若x单调右移后左移 = 输入生效。"""
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client2 import (SokuTrainerInstance, CHAR_REIMU, GameEnded)  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    inst = SokuTrainerInstance(20780)
    print("PID=%s 握手OK" % inst.proc.pid)

    # 前置: SELECT(3)踢回TITLE(2) + 战斗期回填输入表
    import ctypes
    import threading
    import struct
    k32 = ctypes.windll.kernel32
    SCENE = 0x8A0044
    h = k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False,
                        inst.proc.pid)
    stop_kick = threading.Event()

    def kicker():
        tbl = False
        last = None
        while not stop_kick.is_set():
            b = ctypes.create_string_buffer(1)
            g = ctypes.c_size_t()
            if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                     b, 1, ctypes.byref(g)):
                s = b.raw[0]
                if s != last:
                    print("  [kick] scene=%s" % s)
                    last = s
                if s == 5 and not tbl:
                    rl = ctypes.create_string_buffer(4)
                    if k32.ReadProcessMemory(ctypes.c_void_p(h),
                                             ctypes.c_void_p(0x8985E4), rl, 4,
                                             ctypes.byref(g)) and g.value == 4:
                        bm = struct.unpack("<I", rl.raw)[0]
                        if 0x10000 < bm < 0x80000000 and \
                           k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(bm + 0x0C), rl, 4, ctypes.byref(g)) and g.value == 4:
                            cm = struct.unpack("<I", rl.raw)[0]
                            if 0x10000 < cm < 0x80000000 and \
                               k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(cm + 0x750), rl, 4, ctypes.byref(g)) and g.value == 4:
                                kmgr = struct.unpack("<I", rl.raw)[0]
                                km = ctypes.create_string_buffer(4)
                                if 0x10000 < kmgr < 0x80000000 and \
                                   k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(kmgr), km, 4, ctypes.byref(g)) and g.value == 4:
                                    v = struct.unpack("<I", km.raw)[0]
                                    if 0x10000 < v < 0x80000000:
                                        k32.WriteProcessMemory(
                                            ctypes.c_void_p(h),
                                            ctypes.c_void_p(0x898680),
                                            struct.pack("<II", v, v), 8, None)
                                        tbl = True
                                        print("  [kick] 输入表已回填")
            stop_kick.wait(0.3)

    threading.Thread(target=kicker, daemon=True).start()
    # mod已改为TITLE/SELECT双放行+直接驱动LOADING — 无需再踢
    time.sleep(0.5)

    inst.start_vs_com(CHAR_REIMU, CHAR_REIMU)
    print("开局OK, 等战斗帧...")

    frames = 0
    xs = []
    phase = "baseline"
    t0 = time.time()
    while time.time() - t0 < 40:
        try:
            left, right, weather, objs = inst.recv_frame(timeout=60.0 if frames == 0 else 2.0)
        except GameEnded as ge:
            print("结束@%d: %s" % (frames, ge))
            break
        except TimeoutError:
            print("超时@%d" % frames)
            break
        frames += 1
        xs.append((frames, left["hp"], left["position.x"]))
        if frames == 240:
            phase = "right"
        elif frames == 420:
            phase = "left"
        elif frames == 540:
            phase = "none"
        # 锁步协议: 每帧必发输入包(baseline=空)
        if phase == "right":
            inst.send_inputs({"H": 1}, {})
        elif phase == "left":
            inst.send_inputs({"H": -1}, {})
        else:
            inst.send_inputs({}, {})
        if frames % 60 == 0:
            print("帧%d [%s] hp=%s x=%.0f" % (frames, phase, left["hp"],
                                              left["position.x"]))
    # 分析
    def x_at(f):
        for fr, hp, x in xs:
            if fr >= f:
                return x
        return None

    print()
    print("基线末(240): x=%s" % (x_at(240) and round(x_at(240))))
    print("右移末(420): x=%s (Δ=%s)" % (x_at(420) and round(x_at(420)),
          x_at(420) and x_at(240) and round(x_at(420) - x_at(240))))
    print("左移末(540): x=%s (Δ=%s)" % (x_at(540) and round(x_at(540)),
          x_at(540) and x_at(420) and round(x_at(540) - x_at(420))))
    inst.close()


if __name__ == "__main__":
    main()
