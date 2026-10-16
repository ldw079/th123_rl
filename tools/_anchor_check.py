# -*- coding: utf-8 -*-
"""一次性: 干跑锚点校验 — 全部MUTATIONS的old串仍在当前源码中命中。
(不建沙箱不跑门禁, 秒级; 供满负荷期替代完整变异自检的锚点面核查)"""
import ast
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
src = io.open(os.path.join(HERE, 'gate_selftest.py'),
              encoding='utf8').read()
m = re.search(r'MUTATIONS = \[(.*?)\n\]\n', src, re.S)
body = m.group(1)
entries = re.findall(
    r'\(\s*"([^"]+)",\s*"((?:[^"\\]|\\.)*)"'
    r'\s*,\s*"((?:[^"\\]|\\.)*)"\s*,\s*"([^"]+)"\s*\)', body)
print('parsed mutations:', len(entries))
stale = []
for f, old, new, why in entries:
    p = os.path.join(ROOT, f)
    if not os.path.exists(p):
        if f == 'ModLoaderSettings.json':
            continue   # 已知假阳性: 沙箱注入件, 非仓内文件
        stale.append((f, 'FILE_MISSING', why[:40]))
        continue
    txt = io.open(p, encoding='utf8').read()
    try:
        old_lit = ast.literal_eval('"%s"' % old)
    except Exception:
        old_lit = old
    if txt.count(old_lit) < 1:
        stale.append((f, old_lit[:60], why[:50]))
print('stale (pattern no longer in source):', len(stale))
for s in stale:
    print('  ', s)
