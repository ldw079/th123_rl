# -*- coding: utf-8 -*-
"""v8验证(忠实复刻版): 注入 → calls计数(活回合应≈124/s) → P2右/P1右位移。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import bridge_inject  # noqa: E402
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

bridge_inject.DLL_PATH = r"%USERPROFILE%\Desktop\workplace\th123_rl\input_bridge8.dll"
RIGHT = 0x08

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main(pid):
    sen = HudSensor(pid)
    ctl = BridgeCtl(pid)
    ctl.dll_path = bridge_inject.DLL_PATH.encode()
    print("注入v8 + BridgeInit (PID=%d)..." % pid)
    ctl.inject()

    c1 = ctl._rd(20)
    time.sleep(1.0)
    c2 = ctl._rd(20)
    print("detour调用: %d → %d (Δ=%d)" % (c1, c2, c2 - c1))
    if c2 == c1:
        print("!! detour未触发 — 回合非活")
        ctl.close()
        return

    s = sen.read()
    x2_0 = s["battle"]["right"]["x"]
    x1_0 = s["battle"]["left"]["x"]
    print("P1x=%.0f P2x=%.0f → 后台按住P2右 1.8s..." % (x1_0, x2_0))
    ctl._wr(8, RIGHT)
    ctl._wr(16, 1)
    time.sleep(1.8)
    ctl._wr(8, 0)
    time.sleep(0.3)
    s = sen.read()
    x2_1 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    d2 = (x2_1 - x2_0) if (x2_1 is not None and x2_0 is not None) else None
    print("P2x: %.0f → %s Δ=%s %s" % (x2_0, round(x2_1) if x2_1 else None,
                                       round(d2) if d2 is not None else None,
                                       "<<< P2动了!!!" if d2 and abs(d2) > 5 else ""))

    s = sen.read()
    x1_0 = s["battle"]["left"]["x"] if s and s.get("battle") else None
    print("后台按住P1右 1.8s...")
    ctl._wr(0, RIGHT)
    ctl._wr(16, 1)
    time.sleep(1.8)
    ctl._wr(0, 0)
    ctl._wr(16, 0)
    time.sleep(0.3)
    s = sen.read()
    x1_1 = s["battle"]["left"]["x"] if s and s.get("battle") else None
    d1 = (x1_1 - x1_0) if (x1_1 is not None and x1_0 is not None) else None
    print("P1x: %s → %s Δ=%s %s" % (round(x1_0) if x1_0 else None,
                                     round(x1_1) if x1_1 else None,
                                     round(d1) if d1 is not None else None,
                                     "<<< P1动了!!!" if d1 and abs(d1) > 5 else ""))
    ctl.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 39208)
