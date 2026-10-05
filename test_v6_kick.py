# -*- coding: utf-8 -*-
"""v6焦点欺骗踢醒测试(13916, 已注入):
PostMessage(WM_NULL)唤醒沉睡的消息泵 → pump hook注入激活三连 →
游戏开始轮询GetKeyboardState(看到我们的合成态) → P2右键位移验证。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from bridge_inject import BridgeCtl, BIT  # noqa: E402
from hud_sensor import HudSensor  # noqa: E402

PID = 13916
WM_NULL = 0x0000

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_hwnd(pid):
    from capture import find_windows
    u32 = ctypes.windll.user32
    for hwnd, title in find_windows("非想天"):
        p = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            return hwnd
    return None


def main():
    hwnd = find_hwnd(PID)
    print("PID=%d HWND=0x%X" % (PID, hwnd or 0))
    sen = HudSensor(PID)
    s = sen.read()
    if not s or not s.get("battle"):
        print("不在对局")
        return
    x0 = s["battle"]["right"]["x"]
    print("P2(右)x0=%.1f" % x0)

    ctl = BridgeCtl(PID)
    ctl.open_map()
    k1, act1 = ctl._rd(16), ctl._rd(80)
    print("注入前: kbstate=%d activation_sent=%d" % (k1, act1))

    # 激活请求 + 踢醒循环
    ctl.activate(hwnd)
    u32 = ctypes.windll.user32
    t0 = time.time()
    kicked = 0
    while time.time() - t0 < 2.0:
        u32.PostMessageW(ctypes.c_void_p(hwnd), WM_NULL, 0, 0)
        kicked += 1
        time.sleep(1.0 / 60)
    k2, act2 = ctl._rd(16), ctl._rd(80)
    print("踢醒%d次后: kbstate=%d→%d activation_sent=%d→%d"
          % (kicked, k1, k2, act1, act2))

    if k2 == k1:
        print("!! 踢醒后游戏仍未轮询输入")
        ctl.close()
        return

    # P2右键持续按住, 继续踢醒
    print("按住P2右键1.8s(持续踢醒)...")
    ctl.set_keys(BIT["right"])
    t0 = time.time()
    while time.time() - t0 < 1.8:
        u32.PostMessageW(ctypes.c_void_p(hwnd), WM_NULL, 0, 0)
        time.sleep(1.0 / 60)
    ctl.release()
    time.sleep(0.3)

    s2 = sen.read()
    x1 = s2["battle"]["right"]["x"] if s2 and s2.get("battle") else None
    print("P2(右)x: %.1f → %s | 伪造事件=%d" % (x0, x1, ctl._rd(60)))
    if x1 is not None and abs(x1 - x0) > 1.0:
        print(">>> 成功: 后台实例收到输入, P2动了!")
    else:
        print(">>> 角色未动(轮询已开始但状态没被采用, 看事件计数)")
    ctl.close()


if __name__ == "__main__":
    main()
