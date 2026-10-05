# -*- coding: utf-8 -*-
"""解析训练目录崩溃dump: 异常码/地址/模块/线程栈。"""
import sys

from minidump.minidumpfile import MinidumpFile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

f = MinidumpFile.parse(r"D:\touhou\hisoutensoku2026-06-15\th123_train\crashes\crash_2026-09-21-23-57-55.dmp")

print("=== 异常 ===")
ex_addr = None
ctx_tid = None
if f.exception:
    for er in f.exception.exception_records:
        er2 = er.ExceptionRecord if hasattr(er, "ExceptionRecord") else er
        code_raw = getattr(er2, "ExceptionCode", 0)
        code = int(getattr(code_raw, "value", code_raw) or 0)
        addr = getattr(er2, "ExceptionAddress", None)
        addr = int(addr) if addr is not None else None
        tid = getattr(er2, "ThreadId", None) or getattr(er, "ThreadId", None)
        tid = int(tid) if tid is not None else None
        print("code=0x%X addr=%s tid=%s" % (code,
              "0x%X" % addr if addr else "?", tid))
        ex_addr = ex_addr or addr
        ctx_tid = ctx_tid or tid
else:
    print("(无异常记录)")

print("=== 模块 ===")
mods = {}
for m in f.modules.modules:
    mods[m.baseaddress] = (m.name, m.size)
    if "Soku" in m.name or "th123" in m.name.lower() or "giuroll" in m.name:
        print("0x%08X %6dKB %s" % (m.baseaddress, m.size // 1024, m.name))

ex_addr = ex_addr
if ex_addr:
    hit = [v for k, v in mods.items() if k <= ex_addr < k + v[1]]
    print("异常地址所在模块: %s" % (hit[0][0] if hit else "未知(0x%X)" % ex_addr))
    if hit:
        base = [k for k in mods if mods[k] == hit[0]][0]
        print("模块内偏移: +0x%X" % (ex_addr - base))

print("=== 线程栈 ===")
try:
    import struct
    for t in f.threads.threads:
        if ctx_tid is not None and t.ThreadId != ctx_tid:
            continue
        print("ThreadId=%s" % t.ThreadId)
        sp = t.Stack.StartOfMemoryRanges if hasattr(t.Stack, "StartOfMemoryRanges") else t.Stack.StartOfMemoryRange
        try:
            raw = f.get_reader().read(sp, 0x200)
        except Exception:
            continue
        found = []
        for i in range(0, len(raw) - 4, 4):
            v = struct.unpack_from("<I", raw, i)[0]
            for k, (name, size) in mods.items():
                if k <= v < k + size:
                    found.append((name, v - k))
                    break
        seen = set()
        for name, off in found[:40]:
            key = (name, off)
            if (name, off // 0x1000) in seen:
                continue
            seen.add((name, off // 0x1000))
            print("  %s +0x%X" % (name, off))
except Exception as ex:
    print("栈解析失败: %s" % ex)
