# -*- coding: utf-8 -*-
"""v3全量标签分布top20(后采样)."""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')

import bc_build
from train_tm import CHAR_LIBS

orig = bc_build.StreamMatcher
bc_build.StreamMatcher = lambda macros, threshold=0.85: \
    orig(macros, threshold=threshold, mode='v3')
shards = sorted(glob.glob(os.path.join(
    ROOT, 'data', 'oracle_v2', 'shards', '*.npz')))[:40]
name, rows, st = bc_build.build_rows(0, shards, log=lambda *a: None)
X, S, Y, C = rows
names = [m[0] for m in CHAR_LIBS['reimu']['macros']]
cnt = np.bincount(Y, minlength=len(names))
print('v3后采样总行:', len(Y))
order = sorted(range(len(names)), key=lambda k: -cnt[k])
for i in order[:20]:
    if cnt[i]:
        print('  %-10s %5d (%4.1f%%)' % (names[i], cnt[i], cnt[i] / len(Y) * 100))
