# -*- coding: utf-8 -*-
"""一次性: S布局探针v2(绝对列=2n+core偏移 — 首版漏加2n)."""
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, '.')

from bc_io import load_bank

X, S, Y = load_bank('reimu', store=r'D:/temp/th123_models')
n = 88          # reimu宏数
O = 2 * n       # core偏移=176
S_arr = np.asarray(S[:30000])
print('core[4](adx/600)分位px:',
      [int(np.percentile(S_arr[:, O + 4], p) * 600)
       for p in (10, 25, 50, 75, 90)])
print('贴角位非零率: opp=%.4f own=%.4f' % (
    float((S_arr[:, O + 149] > 0.01).mean()),
    float((S_arr[:, O + 150] > 0.01).mean())))
c = Counter()
for row in S_arr:
    oid = None
    for o in (0, 1, 2):
        if row[O + 227 + o] > 0.9:
            oid = o
            break
    if oid is None:
        for j in range(11, 20):
            if row[O + 227 + j] > 0.9:
                oid = j
                break
    if oid is None:
        for k in range(8):
            if row[O + 308 + k] > 0.9:
                oid = 20 + k
                break
    c[oid] += 1
print('对位分布(绝对列% d):' % (O + 227), dict(c.most_common(8)))
