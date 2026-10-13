# -*- coding: utf-8 -*-
"""W4(研究借鉴方案§4): 价值轨迹曲线 — "原因-放大-兑现"的值读数.

learner批路径观测挂点(与series_meter同款try/except降级, 降级必须响亮):
no_grad批前向值头 → 每episode值轨迹按every帧降采样 → 分局胜负聚合
出均值线(grep口径: 价值曲线), 三段(早/中/晚≈原因/放大/兑现)留npz档。

验收(方案§W4): 领先局曲线均值显著高于均势局(2σ, 合成episode断言);
仪表失败不阻断批。
"""
from __future__ import annotations

import numpy as np


def episode_values(net, arr, every=30, chunk=512):
    """单episode值轨迹 → [(帧号, v), ...] 按every帧降采样。

    torch导入失败/前向异常由调用方try捕获并响亮降级(不静默)。
    net(X,S)返回(logits, value, opp)三态(net.forward契约)。
    """
    import torch
    feats = np.asarray(arr['feats'])
    sides = np.asarray(arr['sides'])
    idx = list(range(0, len(feats), every))
    if not idx:
        return []
    out = []
    with torch.no_grad():
        for i0 in range(0, len(idx), chunk):
            sub = idx[i0:i0 + chunk]
            X = torch.from_numpy(
                np.ascontiguousarray(feats[sub])).float()
            S = torch.from_numpy(
                np.ascontiguousarray(sides[sub])).float()
            r = net(X, S)
            v = r[1] if isinstance(r, (tuple, list)) else r['value']
            out.extend(float(x) for x in
                       v.detach().cpu().numpy().ravel())
    return list(zip(idx, out))


def thirds_mean(traj):
    """轨迹三段均值(早/中/晚 — 原因/放大/兑现的近似分位)。

    返回(early, mid, late); 段不足时该位为None。
    """
    if not traj:
        return None, None, None
    vals = [v for _f, v in traj]
    n = len(vals)
    if n < 3:
        return (float(np.mean(vals)), None, None)
    k = n // 3
    return (float(np.mean(vals[:k])), float(np.mean(vals[k:2 * k])),
            float(np.mean(vals[2 * k:])))


def value_line(recs):
    """[(traj, outcome)] → 汇总行。W局与L局分开报均值+样本数 —
    验收看W局均值显著高于L局(值头对结果的前瞻性, 2σ判读在测试侧)。"""
    agg = {'W': [], 'L': []}
    for traj, outcome in recs:
        if traj and outcome in ('W', 'L'):
            agg[outcome].append(
                float(np.mean([v for _f, v in traj])))
    parts = ['价值曲线']
    for oc in ('W', 'L'):
        vs = agg[oc]
        parts.append('%s局均值%s(n%d)' % (
            oc, ('%.3f' % float(np.mean(vs))) if vs else '-',
            len(vs)))
    return ' '.join(parts)
