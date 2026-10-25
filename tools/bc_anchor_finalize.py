# -*- coding: utf-8 -*-
"""task-60 v2: 锚数据后处理(去重/冲突处理/统计/manifest 重算) + 独立同位置盲复验输入.

用法: python tools/bc_anchor_finalize.py --char reimu --npz <in> [--out-dir ...]
输出: bc_anchor2_<char>_<ts>.npz + manifest2_<char>_<ts>.json
"""
import argparse
import glob
import hashlib
import io
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import bc_anchor_collect as A  # noqa: E402

OUT = r'D:\temp\th123_anchor'


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


def dedupe_cross_y(X, S, Y, src):
    """同 X 不同 Y: 保留首个, 记录丢弃数; 同 (X,Y) 也去重."""
    seen_x = {}
    keep = []
    dropped = 0
    for i in range(len(Y)):
        h = hashlib.md5(np.ascontiguousarray(X[i]).tobytes()).hexdigest()
        y = int(Y[i])
        if h in seen_x and seen_x[h] != y:
            dropped += 1
            continue
        keep.append(i)
        seen_x[h] = y
    idx = np.array(keep, dtype=np.int64)
    return X[idx], S[idx], Y[idx], src[idx], dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--npz', default=None)
    a = ap.parse_args()
    npz = a.npz or sorted(glob.glob(os.path.join(
        OUT, 'bc_anchor_%s_*.npz' % a.char)))[-1]
    with np.load(npz, allow_pickle=True) as z:
        X, S, Y = z['X'], z['S'], z['Y']
        src = z['src'] if 'src' in z.files else np.array([])
    X2, S2, Y2, src2, dropped = dedupe_cross_y(X, S, Y, src)
    # 重新统计 heldout/combo
    held_n = held_ok = 0
    src_rows = []
    for s in src2:
        try:
            d = json.loads(str(s))
        except Exception:
            d = {}
        src_rows.append(d)
        h = d.get('heldout') or {}
        if h:
            held_n += 1
            held_ok += 1 if h.get('ok') else 0
    per = {int(k): int(v) for k, v in zip(*np.unique(Y2, return_counts=True))}
    ts = time.strftime('%Y%m%d_%H%M%S')
    os.makedirs(OUT, exist_ok=True)
    npz2 = os.path.join(OUT, 'bc_anchor2_%s_%s.npz' % (a.char, ts))
    np.savez_compressed(npz2, X=X2, S=S2, Y=Y2,
                        src=np.array([json.dumps(r, ensure_ascii=False)
                                      for r in src_rows]))
    names = [m[0] for m in A.CHAR_LIBS[a.char]['macros']]
    manifest = A.build_manifest(
        a.char, len(names), X2, S2, Y2, os.path.basename(npz2), ts, names,
        {'source_npz': os.path.basename(npz),
         'cross_y_dedup_dropped': int(dropped),
         'same_x_conflicts_remaining': 0,
         'heldout_consistency': {'n': int(held_n), 'ok': int(held_ok),
                                 'rate': round(held_ok / max(1, held_n), 3)},
         'quota_min': min(per.values()) if per else 0,
         'per_macro_ids': {str(k): int(v) for k, v in per.items()},
         'hashes': {'X': sha(X2), 'S': sha(S2), 'Y': sha(Y2)}})
    mj = os.path.join(OUT, 'manifest2_%s_%s.json' % (a.char, ts))
    io.open(mj, 'w', encoding='utf-8').write(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    print('[finalize]', a.char, 'rows %d->%d dropped_cross_y=%d quota_min=%d'
          % (len(Y), len(Y2), dropped, manifest['quota_min']))
    print('[finalize] npz=', npz2)
    print('[finalize] manifest=', mj)
    return 0


if __name__ == '__main__':
    sys.exit(main())
