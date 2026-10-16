# -*- coding: utf-8;
"""S-7A风格语料构建: 对shard重放OppModel → 收集9×8情境矩阵 → PCA.

真实数据拟合(R4不猜): 语料=每shard每侧的终局情境矩阵。
产出 data/style_pca.npz(components[8,72]+mean[72]) —
style_embedding()消费。

用法: python tools/style_corpus.py [--limit 300]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from bc_build import build_shard                      # noqa: E402
from opp_model import OpponentModel as OppModel                        # noqa: E402
from style_embedding import (fit_pca, save_components,   # noqa: E402
                             _ctx_matrix_norm)
from frame_events import _GUARD_STUN_IDS             # noqa: E402

DT = 10.0 / 62        # 与训练决策拍同拍


def collect_matrices(shard_path):
    """单shard双边重放 → 两个9×8归一矩阵(不足样本返回[])."""
    out = []
    try:
        meta, frames, inputs, ilog = build_shard(shard_path)
    except Exception:
        return out
    if len(frames) < 300:
        return out
    for side in (0, 1):
        # side=0: 我=左 对手=右; side=1: 我=右 对手=左
        m = OppModel()
        prev_x = {}
        for i, (left, right, weather, objs) in enumerate(frames):
            me, opp = (left, right) if side == 0 else (right, left)
            if i % 3:            # ~20fps采样(决策拍粒度)
                continue
            dx = abs(opp['position.x'] - me['position.x'])
            vx = 0.0
            k = ('x', side)
            if k in prev_x:
                vx = opp['position.x'] - prev_x[k]
            prev_x[k] = opp['position.x']
            m.update(DT * 3, opp.get('airBorne', False),
                     opp.get('action', 0), dx, vx,
                     opp.get('spirit', 1000),
                     len([c for c in (opp.get('hand') or b'')
                          if c != 0xFF]),
                     opp.get('cardGauge', 0), opp['position.x'],
                     _GUARD_STUN_IDS, me.get('airBorne', False),
                     opp.get('action', 0) in (88, 89, 97, 98))
        if sum(m.ctx_total) > 5.0:     # 有实质观测
            out.append(_ctx_matrix_norm(m.ctx, m.ctx_total).reshape(-1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=400)
    a = ap.parse_args()
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:a.limit]
    mats = []
    for i, sp in enumerate(shards):
        mats.extend(collect_matrices(sp))
        if (i + 1) % 50 == 0:
            print('  %d/%d shards → %d矩阵' % (i + 1, len(shards),
                                               len(mats)))
    print('语料: %d个9×8矩阵 (来自%d shards)' % (len(mats), len(shards)))
    assert len(mats) >= 50, '语料不足(%d) — 扩大limit' % len(mats)
    X = np.stack(mats)
    comp, mean = fit_pca(X, n_comp=8)
    evr = None
    # 方差解释率(诊断)
    Xc = X - mean
    tot = float((Xc ** 2).sum())
    proj = Xc @ comp.T
    evr = (float((proj ** 2).sum()) / tot) if tot > 0 else 0
    print('top-8方差解释率: %.1f%%' % (evr * 100))
    save_components(comp, mean)
    print('组件已存: data/style_pca.npz')


if __name__ == '__main__':
    main()
