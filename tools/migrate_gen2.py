# -*- coding: utf-8 -*-
"""migrate_gen2.py — Gen-2 A 特征迁移(CORE 382→391): 模型侧向量/BC 尾部插零.

用法:
  python tools/migrate_gen2.py --dry            # 只打印计划
  python tools/migrate_gen2.py                  # 备份+迁移三模型+BC
仅处理:
  - 模型 npz: W_side/Ws1.weight/W1v 在侧向量段尾部插 9 行零(其余不变)
  - BC: bc_<ch>_S.npy 行尾插 9 列零(5N+382 → 5N+391)
不处理: 快照/对手池(旧宽将被维度守卫拒载 → 回退生产模型, 记录; 可重播种).
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
import time

import numpy as np


def expand_side_arrays(d, n_out, trunk_flat, opp_h2, tail=9):
    """在侧向量段尾部插入 tail 行零; 返回新 dict(不修改原 d)."""
    old = 2 * n_out + 382
    new = old + tail
    out = {}
    for k, v in d.items():
        a = np.asarray(v)
        if k in ('W_side', 'Ws1') or (k.endswith('.weight') and k.startswith(
                'Ws1')):
            if a.ndim == 2 and a.shape[0] == old:
                z = np.zeros((tail, a.shape[1]), dtype=a.dtype)
                _cut = 2 * n_out + 382   # 新维=core 尾部
                out[k] = np.concatenate([a[:_cut], z,
                                         a[_cut:]], axis=0)
                continue
        if k == 'W1v' and a.ndim == 2 and a.shape[0] == trunk_flat + old + opp_h2:
            off = trunk_flat + 2 * n_out + 382
            z = np.zeros((tail, a.shape[1]), dtype=a.dtype)
            out[k] = np.concatenate([a[:off], z, a[off:]], axis=0)
            continue
        out[k] = a
    return out


def pad_bc_S(s, tail=9):
    z = np.zeros((s.shape[0], tail), dtype=s.dtype)
    return np.concatenate([s, z], axis=1)


def plan_model(d, n_out=None):
    if n_out is None:
        n_out = int(np.asarray(d['W_side']).shape[1])
    old = 2 * n_out + 382
    return n_out, old


def plan_value_only(d, n_out, trunk_flat=2560, opp_h2=16):
    rows = int(np.asarray(d['W1v']).shape[0])
    trunk = rows - (2 * n_out + 382) - opp_h2
    return n_out, 2 * n_out + 382, trunk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--store', default=r'D:\temp\th123_models')
    ap.add_argument('--chars', default='reimu,marisa,suika')
    a = ap.parse_args()
    ts = time.strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(a.store, 'p2gen2_backup_%s' % ts)
    todo = []
    for ch in a.chars.split(','):
        for pat in ('model_ppo_%s_fleet.npz' % ch,
                    'model_ppo_%s_fleet_v.npz' % ch):
            p = os.path.join(a.store, pat)
            if os.path.exists(p):
                todo.append(('model', ch, p))
        for pat in ('bc_%s_S.npy' % ch,):
            p = os.path.join(a.store, pat)
            if os.path.exists(p):
                todo.append(('bc', ch, p))
    print('[gen2] plan: %d 文件, 备份→%s' % (len(todo), backup))
    for kind, ch, p in todo:
        print('  ', kind, ch, p)
    if a.dry:
        _n_out = {}
        for ch in a.chars.split(','):
            pm = os.path.join(a.store, 'model_ppo_%s_fleet.npz' % ch)
            if os.path.exists(pm):
                _n_out[ch] = int(np.asarray(np.load(pm)['W_side']).shape[1])
        for kind, ch, p in todo:
            if kind == 'model':
                d = np.load(p, allow_pickle=True)
                if 'W_side' not in d.files:
                    if 'W1v' not in d.files:
                        print('  [dry] %s 无侧向量键, 跳过' % os.path.basename(p))
                        continue
                    _, old, trunk = plan_value_only(d, _n_out[ch])
                    print('  [dry] %s value-only W1v=%s (trunk=%d)' % (
                        os.path.basename(p), np.asarray(d['W1v']).shape,
                        trunk))
                    continue
                n_out, old = plan_model(d)
                print('  [dry] %s n_out=%d side=%d→%d' % (
                    os.path.basename(p), n_out, old, old + 9))
            else:
                S = np.load(p)
                print('  [dry] %s S=%s→%s' % (
                    os.path.basename(p), S.shape,
                    (S.shape[0], S.shape[1] + 9)))
        return 0
    os.makedirs(backup, exist_ok=True)
    for kind, ch, p in todo:
        shutil.copy2(p, os.path.join(backup, os.path.basename(p)))
    for kind, ch, p in todo:
        if kind == 'model':
            d = np.load(p, allow_pickle=True)
            if 'W_side' not in d.files:
                if 'W1v' not in d.files:
                    print('[gen2] skip (no side keys):',
                          os.path.basename(p))
                    continue
                _, _, trunk = plan_value_only(d, _n_out[ch])
                n_out = _n_out[ch]
                old = 2 * n_out + 382
                nv = expand_side_arrays(dict(d), n_out, trunk, 16)
                np.savez(p + '.tmp.npz', **nv)
                os.replace(p + '.tmp.npz', p)
                print('[gen2] value model migrated:',
                      os.path.basename(p))
                continue
            n_out, old = plan_model(d)
            trunk = int(np.asarray(d['W1v']).shape[0]) - old - 16
            nv = expand_side_arrays(dict(d), n_out, trunk, 16)
            outp = p + '.tmp.npz'
            np.savez(outp, **nv)
            os.replace(outp, p)
            print('[gen2] model migrated:', os.path.basename(p),
                  'side=%d→%d' % (old, old + 9))
        else:
            S = np.load(p)
            np.save(p + '.tmp.npy', pad_bc_S(S))
            os.replace(p + '.tmp.npy', p)
            print('[gen2] bc migrated:', os.path.basename(p),
                  '%s→%s' % (S.shape, (S.shape[0], S.shape[1] + 9)))
    print('[gen2] backup:', backup)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
