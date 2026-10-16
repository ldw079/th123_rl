# -*- coding: utf-8 -*-
"""地面back-hold决策点调试: v3在这些点匹配了什么宏."""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')

from bc_match import StreamMatcher, expert_bits   # noqa: E402
from bc_build import build_shard                  # noqa: E402
from train_tm import CHAR_LIBS                    # noqa: E402

shards = sorted(glob.glob(os.path.join(
    ROOT, 'data', 'oracle_v2', 'shards', '*.npz')))[:12]
lib = CHAR_LIBS['reimu']
names = [m[0] for m in lib['macros']]
m3 = StreamMatcher(lib, threshold=0.88)
m2 = StreamMatcher(lib, threshold=0.88, mode='v2')

n_dbg = 0
for sp in shards:
    meta, frames, inputs, ilog = build_shard(sp)
    if ilog is None or meta.get('char_x') != 0:
        continue
    u16 = ilog[0]
    fr = frames
    # 找纯left(无按钮)保持>=6帧的段
    bits = [expert_bits(u) for u in u16]
    i = 60
    while i < len(bits) - 8 and n_dbg < 14:
        if bits[i][0] == -1 and not any(bits[i][2:]):   # H=left, 无按钮
            j = i
            while j < len(bits) and bits[j][0] == -1 and not any(bits[j][2:]):
                j += 1
            if j - i >= 6:
                # v3/v2在该点的匹配
                facings = [1 if f[0]['direction'] > 0 else -1 for f in fr]
                h3 = [h for h in m3.walk(u16, facings)
                      if i - 2 <= h[0] <= j]
                h2 = [h for h in m2.walk(u16, facings)
                      if i - 2 <= h[0] <= j]
                print('%s 帧%d-%d left保持%d帧' % (
                    os.path.basename(sp)[:16], i, j, j - i))
                print('   v3: %s' % [(h[0], names[h[1]], round(h[2], 2))
                                     for h in h3])
                print('   v2: %s' % [(h[0], names[h[1]], round(h[2], 2))
                                     for h in h2])
                n_dbg += 1
                i = j
                continue
            i = j
        else:
            i += 1
    if n_dbg >= 14:
        break
