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


def expand_side_arrays(d, n_out, old_side, tail=9):
    """侧向量(=5N+CORE)末端追加 tail 行零; W1v 在 trunk+old_side 处插零."""
    out = {}
    for k, v in d.items():
        a = np.asarray(v)
        if k == 'W_side' or k == 'Ws1' or (k.endswith('.weight')
                                           and k.startswith('Ws1')):
            a = np.asarray(v)
            if a.ndim == 2 and a.shape[0] == old_side:
                z = np.zeros((tail, a.shape[1]), dtype=a.dtype)
                out[k] = np.concatenate([a, z], axis=0)
                continue
        if k == 'W1v' and a.ndim == 2 and a.shape[0] == old_side + 16 + (
                a.shape[0] - old_side - 16):
            _trunk = a.shape[0] - old_side - 16
            off = _trunk + old_side
            z = np.zeros((tail, a.shape[1]), dtype=a.dtype)
            out[k] = np.concatenate([a[:off], z, a[off:]], axis=0)
            continue
        out[k] = a
    return out


def pad_bc_S(s, new_width):
    """BC S 列尾补零到 new_width(=5N+391); 旧宽可能 5N+358/382."""
    if s.shape[1] >= new_width:
        return s
    z = np.zeros((s.shape[0], new_width - s.shape[1]), dtype=s.dtype)
    return np.concatenate([s, z], axis=1)


def plan_model(d, n_out=None):
    if n_out is None:
        n_out = int(np.asarray(d['W_side']).shape[1])
    old_side = int(np.asarray(d['W_side']).shape[0])
    return n_out, old_side


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
        # 2026-10-23: plain 模型也必须迁移(preflight fleet协议测试加载它)
        for pat in ('model_ppo_%s_fleet.npz' % ch,
                    'model_ppo_%s_fleet_v.npz' % ch,
                    'model_ppo_%s.npz' % ch,
                    'model_ppo_%s_v.npz' % ch):
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
                with np.load(p, allow_pickle=True) as _z:
                    d = {k: _z[k] for k in _z.files}
                if 'W_side' not in d:
                    if 'W1v' not in d:
                        print('  [dry] %s 无侧向量键, 跳过' % os.path.basename(p))
                        continue
                    _r = np.asarray(d['W1v']).shape[0]
                    print('  [dry] %s value-only W1v=%s' % (
                        os.path.basename(p), np.asarray(d['W1v']).shape))
                    continue
                n_out, old_side = plan_model(d)
                print('  [dry] %s n_out=%d side=%d→%d' % (
                    os.path.basename(p), n_out, old_side, old_side + 9))
            else:
                S = np.load(p)
                n_out = len(_n_out) and None
                _ch2 = ch
                new_w = 5 * int(np.asarray(np.load(os.path.join(
                    a.store, 'model_ppo_%s_fleet.npz' % _ch2))[
                        'W_side']).shape[1]) + 391
                print('  [dry] %s S=%s→%s' % (
                    os.path.basename(p), S.shape,
                    (S.shape[0], max(S.shape[1], new_w))))
        return 0
    os.makedirs(backup, exist_ok=True)
    for kind, ch, p in todo:
        shutil.copy2(p, os.path.join(backup, os.path.basename(p)))
    for kind, ch, p in todo:
        if kind == 'model':
            with np.load(p, allow_pickle=True) as _z:
                d = {k: _z[k] for k in _z.files}
            if 'W_side' not in d:
                if 'W1v' not in d:
                    print('[gen2] skip (no side keys):',
                          os.path.basename(p))
                    continue
                n_out = int(np.asarray(np.load(os.path.join(
                    a.store, 'model_ppo_%s_fleet.npz' % ch))[
                        'W_side']).shape[1])
                old_side = 5 * n_out + 382
                nv = expand_side_arrays(dict(d), n_out, old_side)
                np.savez(p + '.tmp.npz', **nv)
                os.replace(p + '.tmp.npz', p)
                print('[gen2] value model migrated:',
                      os.path.basename(p))
                continue
            n_out, old_side = plan_model(d)
            nv = expand_side_arrays(dict(d), n_out, old_side)
            np.savez(p + '.tmp.npz', **nv)
            os.replace(p + '.tmp.npz', p)
            print('[gen2] model migrated:', os.path.basename(p),
                  'side=%d→%d' % (old_side, old_side + 9))
        else:
            S = np.load(p)
            n_out = int(np.asarray(np.load(os.path.join(
                a.store, 'model_ppo_%s_fleet.npz' % ch))[
                    'W_side']).shape[1])
            new_w = 5 * n_out + 391
            print('[gen2] bc migrated:', os.path.basename(p),
                  '%s→%s' % (S.shape, (S.shape[0], max(S.shape[1], new_w))))
            _out = pad_bc_S(np.asarray(S), new_w)
            del S
            np.save(p + '.tmp.npy', _out)
            del _out
            os.replace(p + '.tmp.npy', p)
    print('[gen2] backup:', backup)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
