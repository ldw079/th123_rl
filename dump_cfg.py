# -*- coding: utf-8 -*-
"""定向转储游戏配置文件(只读)。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = r"D:\touhou\hisoutensoku2026-06-15\th123"

TEXTS = [
    os.path.join(BASE, "configex123.ini"),
    os.path.join(BASE, "SWRSToys.ini"),
    os.path.join(BASE, "modules", "DPadFix", "DPadFix.ini"),
    os.path.join(BASE, "modules", "giuroll", "giuroll.ini"),
]
BINS = [
    os.path.join(BASE, "config123.dat"),
]


def hexdump(data, limit=768):
    out = []
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i:i + 16]
        hexs = " ".join("%02X" % b for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append("%04X  %-47s  %s" % (i, hexs, asc))
    return "\n".join(out)


def main():
    for p in TEXTS:
        print("=" * 70)
        print("[TEXT]", p)
        try:
            data = open(p, "rb").read()
            for enc in ("utf-8", "gbk"):
                try:
                    text = data.decode(enc)
                    break
                except Exception:
                    text = None
            print(text if text is not None else data.decode("utf-8", errors="replace"))
        except Exception as e:
            print("读取失败:", e)
    for p in BINS:
        print("=" * 70)
        print("[BIN]", p, "size=", os.path.getsize(p))
        try:
            data = open(p, "rb").read()
            print(hexdump(data))
        except Exception as e:
            print("读取失败:", e)


if __name__ == "__main__":
    main()
