# -*- coding: utf-8 -*-
"""防御/移动标签份额探针: v2/v3对 立防/蹲防/空防/结界/前冲/后冲/飞翔
等的标签量, 以及LOW_INFO降采样的实际丢弃比."""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import bc_build
from train_tm import CHAR_LIBS

DEF_MOVE = ['立防', '蹲防', '空防', '结界2', '结界4', '前冲', '后冲',
            '空冲', '空冲后', '飞翔', '空翔前', '空翔后', '后退', '前进']


def run_mode(mode, shards):
    orig = bc_build.StreamMatcher

    def _mk(macros, threshold=0.85):
        return orig(macros, threshold=threshold, mode=mode)
    bc_build.StreamMatcher = _mk
    try:
        name, rows, st = bc_build.build_rows(0, shards, log=lambda *a: None)
    finally:
        bc_build.StreamMatcher = orig
    if rows is None:
        return None
    X, S, Y, C = rows
    return Y


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', '*.npz')))[:n]
    names = [m[0] for m in CHAR_LIBS['reimu']['macros']]
    idx = {nm: i for i, nm in enumerate(names)}
    print('shards: %d (reimu)' % len(shards))
    print('%-6s %-8s %-8s | %-7s %-7s' %
          ('宏', 'v2行', 'v3行', 'v2占比', 'v3占比'))
    ys = {}
    for mode in ('v2', 'v3'):
        ys[mode] = run_mode(mode, shards)
    for nm in DEF_MOVE:
        i = idx.get(nm)
        if i is None:
            print('%-8s (库中无此宏)' % nm)
            continue
        c2 = int((ys['v2'] == i).sum())
        c3 = int((ys['v3'] == i).sum())
        n2, n3 = len(ys['v2']), len(ys['v3'])
        print('%-8s %6d %8d | %5.2f%% %5.2f%%' %
              (nm, c2, c3, c2 / n2 * 100, c3 / n3 * 100))
    print('\n总行数: v2=%d v3=%d' % (len(ys['v2']), len(ys['v3'])))
