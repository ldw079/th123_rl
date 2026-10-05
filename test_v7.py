# -*- coding: utf-8 -*-
"""v7最终验证: 注入detour → 看calls计数(应~124/s=双管理者×62fps)
→ 后台按住P2右1.5s看P2x位移 → P1右验证。无需焦点无需真实键盘。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

PID = 13916
RIGHT = 0x08

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    sen = HudSensor(PID)
    ctl = BridgeCtl(PID)
    print("注入v7 + BridgeInit...")
    ctl.inject()

    c1 = ctl._rd(20)
    time.sleep(1.0)
    c2 = ctl._rd(20)
    print("detour调用: %d → %d (Δ=%d, 预期≈124)" % (c1, c2, c2 - c1))
    if c2 == c1:
        print("!! detour没被调用 — 回合不活或地址错")
        ctl.close()
        return

    s = sen.read()
    if not s or not s.get("battle"):
        print("不在对局")
        ctl.close()
        return
    x1_0 = s["battle"]["left"]["x"]
    x2_0 = s["battle"]["right"]["x"]
    print("P1x=%.0f P2x=%.0f, 后台按住P2右(PgDn位=0x08) 1.8s..." % (x1_0, x2_0))

    ctl._wr(8, RIGHT)     # p2bits
    ctl._wr(16, 1)        # active
    time.sleep(1.8)
    ctl._wr(8, 0)
    time.sleep(0.3)
    s = sen.read()
    x2_1 = s["battle"]["right"]["x"] if s and s.get("battle") else None
    d2 = (x2_1 - x2_0) if (x2_1 is not None and x2_0 is not None) else None
    print("P2x: %.0f → %s Δ=%s %s" % (x2_0, round(x2_1) if x2_1 else None,
                                       round(d2) if d2 is not None else None,
                                       "<<< P2动了!!!" if d2 and abs(d2) > 5 else ""))

    print("再按住P1右 1.8s...")
    s = sen.read()
    x1_0 = s["battle"]["left"]["x"] if s and s.get("battle") else None
    ctl._wr(0, RIGHT)     # p1bits
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
    main()
