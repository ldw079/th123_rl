# -*- coding: utf-8 -*-
"""三实例活性对比: 谁的HP/位置在变(活对局), 谁冻结。"""
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def snap(pid):
    sen = HudSensor(pid)
    s = sen.read()
    if not s or not s.get("battle"):
        return None
    b = s["battle"]
    return (s.get("scene"), b.get("round"), b.get("match_state"),
            int(b["left"]["hp"]), int(b["right"]["hp"]),
            round(b["left"]["x"]), round(b["right"]["x"]))


def main():
    pids = [39208, 40024, 13916]
    for rnd in range(3):
        for pid in pids:
            a = snap(pid)
            time.sleep(1.2)
            bb = snap(pid)
            tag = ""
            if a and bb:
                chg = (a[3] != bb[3] or a[4] != bb[4] or
                       abs(a[5] - bb[5]) > 1 or abs(a[6] - bb[6]) > 1)
                tag = " <<< 活的!" if chg else "(冻结)"
            print("PID=%d %s → %s %s" % (pid, a, bb, tag))
        print("---")


if __name__ == "__main__":
    main()
