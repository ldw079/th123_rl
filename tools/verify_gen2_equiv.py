# -*- coding: utf-8 -*-
"""verify_gen2_equiv.py — 窗#6 迁移等价验证(结构 + 前向 maxdiff).

用法: python tools/verify_gen2_equiv.py --backup <p2gen2_backup_dir> [--store ...]
检查:
  1) 迁移后侧向量权重 = 旧权重在 (2N+382) 处插 9 行零(前段/后段逐位一致);
  2) BC S = 旧 S + 末 9 列零;
  3) 前向等价: GEN2=1 宽 391 模型(新维 0) 与旧宽 382 模型在相同输入上 maxdiff=0.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

TRUNK = None  # 由 W1v 形状反推


def load(p):
    return dict(np.load(p, allow_pickle=True))


def check_model(old, new, name, old_side=None):
    ok = True
    if old_side is None and 'W_side' in old:
        old_side = int(np.asarray(old['W_side']).shape[0])
    if old_side is None:
        print('  [skip] %s 无 old_side' % name)
        return True
    for k in ('W_side', 'Ws1.weight', 'W1v'):
        if k not in old or k not in new:
            continue
        a = np.asarray(old[k])
        b = np.asarray(new[k])
        if k == 'W1v':
            trunk = a.shape[0] - old_side - 16
            cut = trunk + old_side
            same_head = np.array_equal(b[:cut], a[:cut])
            same_tail = np.array_equal(b[cut + 9:], a[cut:])
            zero = float(np.abs(b[cut:cut + 9]).max()) == 0
        else:
            cut = old_side
            same_head = np.array_equal(b[:cut], a[:cut])
            same_tail = np.array_equal(b[cut + 9:], a[cut:])
            zero = float(np.abs(b[cut:cut + 9]).max()) == 0
        ok &= same_head and same_tail and zero
        print('  [%s] %s head=%s tail=%s zero=%s' % (
            'OK' if (same_head and same_tail and zero) else 'FAIL',
            k, same_head, same_tail, zero))
    return ok


def forward_check(ch, backup, store):
    import torch
    import sys as _s
    _s.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
    import ppo_gpu as PG
    pi = os.path.join(store, 'model_ppo_%s_fleet.npz' % ch)
    pv = os.path.join(store, 'model_ppo_%s_fleet_v.npz' % ch)
    opi = os.path.join(backup, 'model_ppo_%s_fleet.npz' % ch)
    opv = os.path.join(backup, 'model_ppo_%s_fleet_v.npz' % ch)
    if not all(os.path.exists(x) for x in (pi, pv, opi, opv)):
        return True
    d_new = dict(np.load(pi, allow_pickle=True))
    d_old = dict(np.load(opi, allow_pickle=True))
    n_new = int(np.asarray(d_new['W_side']).shape[0])
    n_old = int(np.asarray(d_old['W_side']).shape[0])
    n_out = int(np.asarray(d_new['W_side']).shape[1])
    t_new = PG.PPOTrainerGPU(n_side=n_new, n_out=n_out, mem_dim=8)
    t_old = PG.PPOTrainerGPU(n_side=n_old, n_out=n_out, mem_dim=8)
    t_new.load(pi, pv)
    t_old.load(opi, opv)
    torch.manual_seed(0)
    X = torch.randn(4, 3, 60, 80)
    S_old = torch.randn(4, n_old)
    S_new = torch.cat([S_old, torch.zeros(4, 9)], dim=1)
    H = torch.zeros(4, 27)
    with torch.no_grad():
        lo, vo, _, _ = t_old.net(X, S_old, 1.0, None, H=H)
        ln, vn, _, _ = t_new.net(X, S_new, 1.0, None, H=H)
    dlog = float((lo - ln).abs().max())
    dval = float((vo - vn).abs().max())
    print('[forward] %s logit_maxdiff=%.3e value_maxdiff=%.3e'
          % (ch, dlog, dval))
    return dlog < 1e-6 and dval < 1e-6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backup', required=True)
    ap.add_argument('--store', default=r'D:\temp\th123_models')
    ap.add_argument('--forward', action='store_true')
    a = ap.parse_args()
    ok = True
    _old_side = {}
    for _ch in ('reimu', 'marisa', 'suika'):
        _bm = os.path.join(a.backup, 'model_ppo_%s_fleet.npz' % _ch)
        if os.path.exists(_bm):
            with np.load(_bm, allow_pickle=True) as _z:
                if 'W_side' in _z.files:
                    _old_side[_ch] = int(_z['W_side'].shape[0])
    for ch in ('reimu', 'marisa', 'suika'):
        for suf in ('fleet.npz', 'fleet_v.npz'):
            bn = 'model_ppo_%s_%s' % (ch, suf)
            bp = os.path.join(a.backup, bn)
            np_ = os.path.join(a.store, bn)
            if not (os.path.exists(bp) and os.path.exists(np_)):
                continue
            print('[model]', bn)
            ok &= check_model(load(bp), load(np_), bn,
                              _old_side.get(ch))
        bs = os.path.join(a.backup, 'bc_%s_S.npy' % ch)
        ns = os.path.join(a.store, 'bc_%s_S.npy' % ch)
        if os.path.exists(bs) and os.path.exists(ns):
            A = np.load(bs, mmap_mode='r')
            B = np.load(ns, mmap_mode='r')
            same = np.array_equal(B[:, :A.shape[1]], A)
            zero = float(np.abs(B[:, A.shape[1]:]).max()) == 0
            ok &= bool(same and zero)
            print('[bc] %s same=%s zero=%s %s→%s' % (
                ch, same, zero, A.shape, B.shape))
    if getattr(a, 'forward', False):
        for ch in ('reimu', 'marisa', 'suika'):
            try:
                ok &= forward_check(ch, a.backup, a.store)
            except Exception as e:
                print('[forward] %s ERR %r' % (ch, e))
                ok = False
    print('==== gen2 equiv: %s ====' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
