# -*- coding: utf-8 -*-
"""在神AI的地址库/脚本里找输入注入机制。"""
import os
import sys

BASE = r"D:\touhou\hisoutensoku2026-06-15\th123ai"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def scan(path, keys, enc="gbk"):
    try:
        src = open(path, "rb").read().decode(enc, "replace")
    except OSError as e:
        print("skip %s: %s" % (path, e))
        return
    lines = src.splitlines()
    hits = []
    for i, l in enumerate(lines):
        low = l.lower()
        if any(k in low for k in keys):
            hits.append((i + 1, l))
    if hits:
        print("== %s (%d行, 命中%d)" % (path, len(lines), len(hits)))
        for n, l in hits[:40]:
            print("  %5d  %s" % (n, l[:160]))


def main():
    # 1) 地址库
    for fn in ("SwrAddr.ini", "SWRSAddr.ini", "SWRSAddr-110.ini", "SWRSAddr-110A.ini",
               "th123_ai.ini"):
        scan(os.path.join(BASE, fn), ("input", "key", "ctrl"))

    # 2) 神AI脚本里的输入写法
    sdir = os.path.join(BASE, "script")
    n = 0
    for root, dirs, files in os.walk(sdir):
        for f in files:
            p = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            enc = "gbk" if ext in (".ai", ".txt", ".ini") else None
            if ext in (".ai", ".txt", ".ini", ".hsp"):
                scan(p, ("input", "keyinput", "key(", "vkey"))
                n += 1
            if n > 30:
                print("...截断")
                return


if __name__ == "__main__":
    main()
