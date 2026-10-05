# -*- coding: utf-8 -*-
"""扫描 .pf 配置文件的键位区(只读): 查找方向键 DIK 码与手柄按钮编码。"""

import glob
import os
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = r"D:\touhou\hisoutensoku2026-06-15\th123\profile"

# DirectInput 键盘码: 方向键
DIK_ARROWS = {0xC8: "UP", 0xD0: "DOWN", 0xCB: "LEFT", 0xCD: "RIGHT"}
# 常用按键码参考
DIK_NAMES = {0x1E: "A", 0x30: "B", 0x2E: "C", 0x20: "D", 0x12: "E", 0x21: "F",
             0x22: "G", 0x23: "H", 0x17: "I", 0x24: "J", 0x25: "K", 0x26: "L",
             0x32: "M", 0x31: "N", 0x18: "O", 0x19: "P", 0x10: "Q", 0x13: "R",
             0x1F: "S", 0x14: "T", 0x16: "U", 0x2F: "V", 0x11: "W", 0x2D: "X",
             0x15: "Y", 0x2C: "Z", 0x39: "SPACE", 0x1C: "ENTER", 0x01: "ESC"}


def scan(path):
    data = open(path, "rb").read()
    print("=== %s (%d bytes) ===" % (path, len(data)))
    # 头 64 字节
    print("head:", " ".join("%02X" % b for b in data[:64]))
    # 找方向键 DIK 码(DWORD 对齐扫描)
    found = {}
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if v in DIK_ARROWS:
            found.setdefault(DIK_ARROWS[v], off)
        elif v in DIK_NAMES and v not in (0x01,):
            found.setdefault("key:" + DIK_NAMES[v], off)
    print("键位命中(偏移):", {k: hex(v) for k, v in sorted(found.items(), key=lambda x: x[1])})
    # 手柄按钮编码(通常 >= 0x100 且 < 0x100000 的槽值, 只打印相邻两个都在此范围的区域)
    # 打印偏移 0x200 之后所有 >=0x0100 的 DWORD 概览(前 40 个)
    big = []
    for off in range(0x200, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if 0x100 <= v <= 0x200:
            big.append((off, v))
    print("手柄疑似值(>=0x100):", [(hex(o), hex(v)) for o, v in big[:24]])


def main():
    for p in sorted(glob.glob(os.path.join(BASE, "*.pf")), key=os.path.getmtime, reverse=True)[:4]:
        scan(p)


if __name__ == "__main__":
    main()
