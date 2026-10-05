# -*- coding: utf-8 -*-
"""实时监视已注入实例的输入路径计数器(不注入, 只开命名映射读)。
配合人工实验: 用户把该窗口切到前台并按键, 观察哪些计数器亮。"""
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import BridgeCtl  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

FIELDS = [
    (12, "async"), (16, "kbstate"), (20, "keystate"),
    (28, "Peek"), (32, "Get"), (36, "WM_INPUT"), (40, "WM_KEY*"),
]


def main(pid, seconds):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ctl = BridgeCtl(pid)
    ctl.open_map()
    sen = HudSensor(pid)

    print("监视 PID=%d (Ctrl-C停止)" % pid)
    last = {off: ctl._rd(off) for off, _ in FIELDS}
    t0 = time.time()
    while time.time() - t0 < seconds:
        time.sleep(0.5)
        cur = {off: ctl._rd(off) for off, _ in FIELDS}
        deltas = {name: cur[off] - last[off] for off, name in FIELDS}
        last = cur
        hot = {k: v for k, v in deltas.items() if v > 0}
        s = sen.read()
        b = s.get("battle") if s else None
        st = "frame=%s P1x=%s P2x=%s" % (
            b and int(b["frame"]), b and round(b["left"]["x"]), b and round(b["right"]["x"]))
        print("[%5.1fs] %-46s %s" % (time.time() - t0, st, hot if hot else "-"))
    ctl.close()


if __name__ == "__main__":
    main(int(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 60.0)
