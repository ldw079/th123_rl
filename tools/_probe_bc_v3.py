# -*- coding: utf-8 -*-
"""bc_match v3前后对比探针: 同批shard, v2 vs v3 弹幕标签占比/行数/分布."""
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
        return None, st
    X, S, Y, C = rows
    lib = CHAR_LIBS['reimu']
    names = [m[0] for m in lib['macros']]
    bids = [i for i, n in enumerate(names) if n in set(lib.get('bullet', ()))]
    adx = S[:, 2 * len(names) + 5]
    far = adx >= 330 / 600
    glob_bl = sum((Y == b).sum() for b in bids) / len(Y) * 100
    far_bl = (sum((Y[far] == b).sum() for b in bids)
              / max(int(far.sum()), 1) * 100)
    dist = sorted(np.bincount(Y, minlength=len(names)).tolist(),
                  reverse=True)[:6]
    top = [(names[i], int(c)) for i, c in
           sorted(enumerate(np.bincount(Y, minlength=len(names)).tolist()),
                  key=lambda x: -x[1])[:6]]
    return {'rows': len(Y), 'bullet_glob%': round(glob_bl, 2),
            'bullet_far%': round(far_bl, 2), 'far_rows': int(far.sum()),
            'top6': top}, st


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', '*.npz')))[:n]
    print('shards: %d' % len(shards))
    for mode in ('v2', 'v3'):
        r, st = run_mode(mode, shards)
        print('\n[%s] %s' % (mode, json.dumps(st, ensure_ascii=False)))
        print(json.dumps(r, ensure_ascii=False))
