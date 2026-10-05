# -*- coding: utf-8 -*-
"""用简单正则核对: 神谕终局比分 vs 文件名比分。"""
import json, re, sys
sys.stdout.reconfigure(encoding='utf8')
rows = [json.loads(ln) for ln in open(
    r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle\manifest_lane0.jsonl',
    encoding='utf8')]
pat = re.compile(r'\((\d)\s*[:︰]\s*(\d)\s*[_\-]?\s*(胜|负)\)')
match = mismatch = unknown = 0
bad = []
for r in rows:
    m = pat.search(r['rep'])
    if not m:
        unknown += 1
        continue
    exp = (int(m.group(1)), int(m.group(2)))
    fin = tuple(r['score_final'])
    if fin == exp:
        match += 1
    else:
        mismatch += 1
        bad.append((r['rep'][:60], fin, exp))
print('有文件名比分: %d 局' % (match + mismatch))
print('一致: %d   不一致: %d   (无比分标记: %d)' % (match, mismatch, unknown))
for b in bad[:15]:
    print('  ✗', b)
