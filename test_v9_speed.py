# -*- coding: utf-8 -*-
"""v9验证(30740新萃香): 注入→基线帧率→tps=4→帧率应×4→P2右驱动仍有效。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import bridge_inject  # noqa: E402
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

bridge_inject.DLL_PATH = r"%USERPROFILE%\Desktop\workplace\th123_rl\input_bridge9.dll"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def frame_rate(sen, seconds):
    a = sen.read()
    f0 = a["battle"]["frame"]
    x0 = a["battle"]["right"]["x"]
    t0 = time.time()
    time.sleep(seconds)
    b = sen.read()
    f1 = b["battle"]["frame"]
    return (f1 - f0) / (time.time() - t0), x0, b


def main(pid):
    sen = HudSensor(pid)
    ctl = BridgeCtl(pid)
    ctl.dll_path = bridge_inject.DLL_PATH.encode()
    print("注入v9 (PID=%d)..." % pid)
    ctl.inject()
    time.sleep(0.5)

    calls0 = ctl._rd(20)
    time.sleep(0.5)
    calls1 = ctl._rd(20)
    print("detour活性: Δ%d/0.5s (回合%s)" % (calls1 - calls0,
                                             "活" if calls1 > calls0 else "不活"))
    if calls1 == calls0:
        print("回合不活, 退出")
        return

    rate1, x0, _ = frame_rate(sen, 1.0)
    print("基线逻辑帧率: %.1f/s" % rate1)

    ctl._wr(28, 4)     # tps=4
    time.sleep(0.5)
    rate4, _, _ = frame_rate(sen, 1.0)
    print("tps=4 逻辑帧率: %.1f/s (倍率=%.1f)" % (rate4, rate4 / max(rate1, 1)))

    ctl._wr(28, 1)     # 回1×
    time.sleep(0.3)

    # 输入仍有效?
    s = sen.read()
    x2_0 = s["battle"]["right"]["x"]
    ctl._wr(8, 0x08)
    ctl._wr(16, 1)
    time.sleep(1.5)
    ctl._wr(8, 0)
    ctl._wr(16, 0)
    time.sleep(0.3)
    s = sen.read()
    x2_1 = s["battle"]["right"]["x"]
    d = x2_1 - x2_0 if x2_1 is not None and x2_0 is not None else None
    print("P2右驱动: Δ=%s %s" % (d and round(d), "OK" if d and abs(d) > 5 else "(未动)"))
    ctl.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30740)
