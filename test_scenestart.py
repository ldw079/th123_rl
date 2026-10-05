# -*- coding: utf-8 -*-
"""程序化开局探测: 读sceneId/newSceneId/主副模式/玩家信息结构,
为"对局结束→外部写场景开新局"铺路。只读。"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

RWX = 0x0010 | 0x0020 | 0x0008 | 0x0400
SCENE = 0x8A0044
SCENE_NEW = 0x8A0040
MAIN_MODE = 0x898690
SUB_MODE = 0x898688

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

k32 = ctypes.windll.kernel32


def rpm(h, a, n):
    b = ctypes.create_string_buffer(n)
    g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(a), b, n,
                                 ctypes.byref(g)) or g.value != n:
        return None
    return b.raw


def main(pid):
    h = k32.OpenProcess(RWX, False, pid)
    sen = HudSensor(pid)
    for i in range(4):
        s = sen.read()
        b = s.get("battle") if s else None
        raw_new = rpm(h, SCENE_NEW, 1)
        print("scene=%s newScene=%s mainMode=%s subMode=%s "
              "round=%s P1hp=%s P2hp=%s P1x=%s"
              % (s and s.get("scene"), raw_new and raw_new[0],
                 struct.unpack("<I", rpm(h, MAIN_MODE, 4) or b"\0\0\0\0")[0],
                 struct.unpack("<I", rpm(h, SUB_MODE, 4) or b"\0\0\0\0")[0],
                 b and b.get("round"),
                 b and b["left"]["hp"], b and b["right"]["hp"],
                 b and round(b["left"]["x"])))
        time.sleep(1.0)
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40024)
