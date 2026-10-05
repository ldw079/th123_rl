# -*- coding: utf-8 -*-
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from hud_sensor import HudSensor  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

k32 = ctypes.windll.kernel32
h = k32.OpenProcess(0x0410, False, 40024)
buf = ctypes.create_string_buffer(8)
got = ctypes.c_size_t()
k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(0x40A45D),
                      buf, 8, ctypes.byref(got))
print("code@0x40A45D:", buf.raw[:8].hex())
sen = HudSensor(40024)
for i in range(3):
    s = sen.read()
    b = s and s.get("battle")
    print("st=%s rd=%s P1x=%s P2x=%s HP=%s/%s" % (
        b and b.get("match_state"), b and b.get("round"),
        b and round(b["left"]["x"]), b and round(b["right"]["x"]),
        b and b["left"]["hp"], b and b["right"]["hp"]))
    time.sleep(1.0)
