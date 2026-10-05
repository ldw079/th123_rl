# -*- coding: utf-8 -*-
"""离线分析 rep 头部未定字段的取值分布(不启动游戏)。"""
import os, collections

root = r'D:\temp\expert_reps'
per_off = {i: collections.Counter() for i in
           list(range(9, 14)) + list(range(60, 63)) + list(range(109, 117))}
n = 0
for dp, _, fs in os.walk(root):
    for fn in fs:
        if not fn.lower().endswith('.rep'):
            continue
        b = open(os.path.join(dp, fn), 'rb').read(121)
        if len(b) < 121 or b[0] != 0xD2:
            continue
        n += 1
        for i in per_off:
            per_off[i][b[i]] += 1

out = ['n = %d' % n]
for i in sorted(per_off):
    top = per_off[i].most_common(8)
    out.append('off %3d: %s' % (i, '  '.join('0x%02X:%d' % (v, c) for v, c in top)))
txt = '\n'.join(out)
open(r'D:\temp\hdr_analysis.txt', 'w').write(txt)
print(txt)
