# -*- coding: utf-8 -*-
"""v8验证-自动守候版: 注入后轮询calls, 检测到活回合立即测P2/P1位移。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import bridge_inject  # noqa: E402
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

bridge_inject.DLL_PATH = r"%USERPROFILE%\Desktop\workplace\th123_rl\input_bridge8.dll"
RIGHT = 0x08
WAIT_S = 300.0

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main(pid):
    sen = HudSensor(pid)
    ctl = BridgeCtl(pid)
    ctl.dll_path = bridge_inject.DLL_PATH.encode()
    print("注入v8 (PID=%d)..." % pid)
    ctl.inject()
    print("守候活回合(最多%ds), 检测到即测..." % WAIT_S)

    t0 = time.time()
    last = 0
    live = False
    while time.time() - t0 < WAIT_S:
        c = ctl._rd(20)
        if c > last + 10:            # 每秒应~124, 10以上=确凿
            live = True
            break
        last = max(last, c)
        time.sleep(0.5)
    if not live:
        print("!! %ds内没等到活回合" % WAIT_S)
        ctl.close()
        return
    print("活回合! calls=%d" % ctl._rd(20))

    s = sen.read()
    x2_0 = s["battle"]["right"]["x"]
    print("P2(右)按右键1.8s...")
    ctl._wr(8, RIGHT)
    ctl._wr(16, 1)
    time.sleep(1.8)
    ctl._wr(8, 0)
    time.sleep(0.3)
    s = sen.read()
    x2_1 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    d2 = (x2_1 - x2_0) if (x2_1 is not None and x2_0 is not None) else None
    print("P2x: %.0f→%s Δ=%s %s" % (x2_0, round(x2_1) if x2_1 else None,
                                     round(d2) if d2 is not None else None,
                                     "<<<成功!!!" if d2 and abs(d2) > 5 else "(未动)"))

    s = sen.read()
    x1_0 = s["battle"]["left"]["x"] if s and s.get("battle") else None
    print("P1(左)按右键1.8s...")
    ctl._wr(0, RIGHT)
    ctl._wr(16, 1)
    time.sleep(1.8)
    ctl._wr(0, 0)
    ctl._wr(16, 0)
    time.sleep(0.3)
    s = sen.read()
    x1_1 = s["battle"]["left"]["x"] if s and s.get("battle") else None
    d1 = (x1_1 - x1_0) if (x1_1 is not None and x1_0 is not None) else None
    print("P1x: %s→%s Δ=%s %s" % (round(x1_0) if x1_0 else None,
                                   round(x1_1) if x1_1 else None,
                                   round(d1) if d1 is not None else None,
                                   "<<<成功!!!" if d1 and abs(d1) > 5 else "(未动)"))
    ctl.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40024)
