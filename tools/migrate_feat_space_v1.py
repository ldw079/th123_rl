# -*- coding: utf-8 -*-
"""task-21 v1 模型迁移: W_side/Ws1 插行 + 值网 W1v 插列(插入点=2N+358).

用法: python tools/migrate_feat_space_v1.py --store D:\\temp\\th123_models
备份: <name>_pre_space_v1.npz.
"""
import argparse
import os
import shutil

import numpy as np

LEGACY_CORE = 358


def expand(npz_path):
    d = dict(np.load(npz_path))
    if 'W_side' in d:
        ws = d['W_side']
        old_side, n_out = ws.shape
    elif 'W1v' in d:
        old_side = int(d['W1v'].shape[0]) - 2560 - 16
        ws = None
    else:
        return False
    if (old_side - LEGACY_CORE) % 5 != 0:
        print('[migrate] 非旧格式, 跳过:', os.path.basename(npz_path), old_side)
        return False
    n_mac = (old_side - LEGACY_CORE) // 5
    ins = 2 * n_mac + LEGACY_CORE
    rng = np.random.default_rng(20261019)

    def ins_rows(a):
        new = rng.normal(0, 0.01, (24, a.shape[1])).astype(a.dtype)
        return np.insert(a, ins, new, axis=0)

    if ws is not None:
        d['W_side'] = ins_rows(ws)
    if 'Ws1' in d and d['Ws1'].shape[0] == old_side:
        d['Ws1'] = ins_rows(d['Ws1'])
    col = 2560 + ins
    if 'W1v' in d:
        w1v = d['W1v']
        if w1v.shape[0] == 2560 + old_side + 16:
            newc = rng.normal(0, 0.01, (24, w1v.shape[1])).astype(w1v.dtype)
            d['W1v'] = np.insert(w1v, col, newc, axis=0)
    if 'Wf1' in d:   # 视觉+侧融合层(npz 存 (in=2560+n_side, out) → 插 24 行)
        wf1 = d['Wf1']
        if wf1.shape[0] == 2560 + old_side:
            newc = rng.normal(0, 0.01, (24, wf1.shape[1])).astype(wf1.dtype)
            d['Wf1'] = np.insert(wf1, col, newc, axis=0)
    bak = npz_path[:-4] + '_pre_space_v1.npz'
    if not os.path.exists(bak):
        shutil.copy2(npz_path, bak)
    np.savez(npz_path, **d)
    print('[migrate] %s: %d→%d (ins@%d)' % (
        os.path.basename(npz_path), old_side, old_side + 24, ins))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default=r'D:\temp\th123_models')
    ap.add_argument('--chars', default='reimu,marisa,suika')
    a = ap.parse_args()
    for ch in a.chars.split(','):
        for suf in ('_fleet', ''):
            for ext in ('.npz', '_v.npz'):
                p = os.path.join(a.store, 'model_ppo_%s%s%s' % (ch, suf, ext))
                if os.path.exists(p) and not p.endswith('_pre_space_v1.npz'):
                    expand(p)
    print('[migrate] done')


if __name__ == '__main__':
    main()
