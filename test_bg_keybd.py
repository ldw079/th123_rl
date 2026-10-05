# -*- coding: utf-8 -*-
"""实验: 全局keybd_event能否被后台实例接收?
若giuroll用WH_KEYBOARD_LL读输入, 则无需焦点, 后台实例也会动。
观察 PID=40024 (后台, 已注入v5计数器) 的P2 x位移。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
import inject  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

PID = 40024
VK_P2_RIGHT = 0x22  # PgDn = KEYMAP2 right

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sen = HudSensor(PID)
s = sen.read()
if not s or not s.get("battle"):
    print("实例不在对局")
    sys.exit(1)
x0 = s["battle"]["right"]["x"]
print("PID=%d 后台实例 P2(右) x0=%.1f, 场景=%s" % (PID, x0, s.get("scene")))

inject.press(VK_P2_RIGHT)
time.sleep(1.8)
inject.release(VK_P2_RIGHT)
time.sleep(0.3)

s2 = sen.read()
x1 = s2["battle"]["right"]["x"] if s2 and s2.get("battle") else None
print("按住PgDn(P2右)1.8s后 x=%s" % x1)
if x1 is not None and abs(x1 - x0) > 1.0:
    print(">>> 后台实例收到全局键盘输入! 无需焦点/注入, giuroll走LL钩子路径")
else:
    print(">>> 后台实例没有反应 — 全局键不被无焦点实例接收")
