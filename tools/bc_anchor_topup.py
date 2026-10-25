# -*- coding: utf-8 -*-
"""task-60: 低配额宏补采（在已有锚 npz 基础上补行，不重生成全量）.

用法: python tools/bc_anchor_topup.py --char suika --npz <base> --min-rows 15
输出: bc_anchor3_<char>_<ts>.npz + manifest3_<char>_<ts>.json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--npz', default=None)
    ap.add_argument('--min-rows', type=int, default=15)
    ap.add_argument('--max-extra-seeds', type=int, default=10)
    ap.add_argument('--port', type=int, default=21102)
    a = ap.parse_args()
    npz = a.npz or sorted(glob.glob(os.path.join(
        OUT, 'bc_anchor_%s_*.npz' % a.char)))[-1]
    with np.load(npz, allow_pickle=True) as z:
        X, S, Y = z['X'], z['S'], z['Y']
        src = list(z['src'])
    names = [m[0] for m in A.CHAR_LIBS[a.char]['macros']]
    macs = A.CHAR_LIBS[a.char]['macros']
    per = {int(k): int(v) for k, v in zip(*np.unique(Y, return_counts=True))}
    need = [i for i, n in enumerate(names)
            if int(per.get(i, 0)) < a.min_rows]
    print('[topup] %s low macros=%s' % (a.char, [names[i] for i in need]))
    if not need:
        print('[topup] no need')
        return 0
    env = A.EvalEnv(a.port, char_left=a.char, char_right=a.char,
                    vs_com=False, tps=360)
    ctx = A.FeatCtx(a.char)
    ts = time.strftime('%Y%m%d_%H%M%S')
    newX, newS, newY, newSrc = [], [], [], []
    try:
        for _ in range(240):
            if A.step(env, dict(A.NEUTRAL), dict(A.NEUTRAL)) is None:
                break
        base_x = {'mid': 420.0, 'corner': 900.0, 'close': 500.0,
                  'air': 480.0, 'wakeup': 500.0}
        base_dx = {'mid': 55.0, 'corner': 70.0, 'close': 40.0,
                   'air': 80.0, 'wakeup': 60.0}
        base_ry = {'mid': 0.0, 'corner': 0.0, 'close': 0.0,
                   'air': 120.0, 'wakeup': 0.0}
        for mid in need:
            got = 0
            target = a.min_rows - int(per.get(mid, 0))
            for seed in range(4, 4 + a.max_extra_seeds):
                for sc in ('mid', 'corner', 'close', 'air', 'wakeup'):
                    if got >= target:
                        break
                    x0 = base_x[sc] + (60 if sc == 'mid' else
                                       -40 if sc == 'corner' else
                                       25 if sc == 'close' else
                                       40 if sc == 'air' else 20) * seed
                    dx = base_dx[sc] + (8 if sc == 'mid' else
                                        -5 if sc == 'corner' else
                                        (9 if sc == 'close' else
                                         12 if sc == 'air' else 8)) * seed
                    try:
                        row = A.capture_row(env, ctx, mid, macs[mid][1],
                                            sc, x0, dx, float(base_ry[sc]),
                                            ts)
                    except Exception:
                        continue
                    if row is None:
                        continue
                    x, s, sr = row
                    newX.append(x)
                    newS.append(s.astype(np.float32))
                    newY.append(mid)
                    newSrc.append(sr)
                    got += 1
            print('  %-10s +%d' % (names[mid], got), flush=True)
    finally:
        try:
            env.close()
        except Exception:
            pass
    if not newY:
        print('[topup] none added')
        return 0
    # 合并 + 去重(X,Y)
    allX = list(X) + newX
    allS = list(S) + newS
    allY = list(Y) + newY
    allSrc = list(src) + newSrc
    AX, AS, AY, ASrc, per2, conflicts = A.finalize_rows(
        allX, allS, allY, allSrc, cap=60)
    npz3 = os.path.join(OUT, 'bc_anchor3_%s_%s.npz' % (a.char, ts))
    np.savez_compressed(npz3, X=AX, S=AS, Y=AY, src=ASrc)
    manifest = A.build_manifest(
        a.char, len(names), AX, AS, AY, os.path.basename(npz3), ts, names,
        {'base_npz': os.path.basename(npz),
         'topup_from': os.path.basename(npz),
         'conflicts': int(conflicts),
         'per_macro': {names[i]: int((AY == i).sum())
                       for i in sorted(set(AY.tolist()))}})
    mj = os.path.join(OUT, 'manifest3_%s_%s.json' % (a.char, ts))
    io.open(mj, 'w', encoding='utf-8').write(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    print('[topup] rows %d->%d conflicts=%d npz=%s'
          % (len(Y), len(AY), conflicts, npz3))
    return 0


if __name__ == '__main__':
    sys.exit(main())
