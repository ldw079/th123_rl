# -*- coding: utf-8 -*-
"""窗口位置↔PID映射(判断哪个窗口在左中右)。只读。"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")

u32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


def main():
    from capture import find_windows
    from hud_sensor import HudSensor
    rows = []
    for hwnd, title in find_windows("非想天"):
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            continue
        rc = RECT()
        u32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rc))
        sen = HudSensor(pid.value)
        s = sen.read()
        b = s.get("battle") if s else None
        rows.append((rc.left, pid.value, hwnd, s and s.get("scene"),
                     b and (round(b["left"]["x"]), round(b["right"]["x"]))))
    rows.sort()
    for i, (x, pid, hwnd, scene, pos) in enumerate(rows):
        print("%s窗: left=%d PID=%d HWND=0x%X scene=%s P1x/P2x=%s"
              % ("左" if i == 0 else ("中" if i == 1 else "右"),
                 x, pid, hwnd, scene, pos))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
