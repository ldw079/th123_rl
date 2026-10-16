# -*- coding: utf-8 -*-
"""S-7A 风格连续嵌入(合并终版方案, P-4重设计 — 不分类, 压缩+条件量).

16维 = 情境矩阵PCA 8 + 漂移 1 + 资源条件差分 4 + 卡组暴露 3。
连续(无离散边界)/情境依赖(PCA作用于9×8矩阵, 不做全局平均)/
动态(输入随EMA演化)/关系性(距离与场地轴天然在矩阵行内)。

PCA组件由真实语料拟合(tools/style_corpus.py 对shard重放收集
9×8情境矩阵 → top-8主成分), 存npz; 投影是确定性点积 — 可重放。
维度11-12(S-2) = PCA投影的前2主成分分数(style_pc1/pc2)。
"""
from __future__ import annotations

import os

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_COMP_PATH = os.path.join(_HERE, 'data', 'style_pca.npz')

N_DIM = 16


def fit_pca(matrices, n_comp=8):
    """对语料(×9×8行归一矩阵)拟合top-n_comp主成分(确定性SVD).

    matrices: (N, 72) — 每行=9×8矩阵展平(行已归一为分布或计数比例)。
    返回components(n_comp, 72), mean(72,)。
    """
    X = np.asarray(matrices, dtype=np.float64)
    mean = X.mean(axis=0)
    U, S, Vt = np.linalg.svd(X - mean, full_matrices=False)
    return Vt[:n_comp].astype(np.float32), mean.astype(np.float32)


def save_components(components, mean, path=None):
    path = path or _COMP_PATH        # 运行时解析(默认参数绑定=定义时快照,
    os.makedirs(os.path.dirname(path), exist_ok=True)  # monkeypatch/改路径不生效)
    tmp = path + '.tmp.npz'
    np.savez(tmp, components=components, mean=mean,
             meta=np.array('style_pca_v1'))
    os.replace(tmp, path)


def load_components(path=None):
    path = path or _COMP_PATH        # 同上(P2测试实证: 原默认参数绑定
    d = np.load(path)                # 使坏档测试静默加载了好档)
    return d['components'], d['mean']


def _ctx_matrix_norm(ctx, ctx_total):
    """9×8计数 → 行归一分布(零样本行=0向量, 保留行位=情境轴)."""
    M = np.asarray(ctx, dtype=np.float64)
    tot = np.asarray(ctx_total, dtype=np.float64)
    out = np.zeros_like(M)
    nz = tot > 1e-9
    out[nz] = M[nz] / tot[nz, None]
    return out


def style_embedding(opp_model_obj, b_seg14, components=None, mean=None):
    """16维风格嵌入(确定性, 可重放).

    opp_model_obj: OppModel实例(读ctx矩阵/_recent/_older/_res_*内部);
    b_seg14: feat_builder B段(对手已出卡追踪14维);
    components/mean: 缺省从data/style_pca.npz加载(语料未建时
    返回None — 调用方以0填充并打警告, 不阻塞训练)。
    """
    if components is None or mean is None:
        if not os.path.exists(_COMP_PATH):
            return None
        components, mean = load_components()
    M = _ctx_matrix_norm(opp_model_obj.ctx, opp_model_obj.ctx_total)
    pca8 = (M.reshape(-1) - mean) @ components.T      # (8,)
    # 漂移1: 近15s与更早分布的L1距离(风格变化率 — 方案D段的drift)
    r = np.asarray(opp_model_obj._recent, dtype=np.float64)
    o = np.asarray(opp_model_obj._older, dtype=np.float64)
    rs = r.sum()
    os_ = o.sum()
    drift = float(np.abs(r / rs - o / os_).sum()) if (
        rs > 1e-9 and os_ > 1e-9) else 0.0
    # 资源条件差分4: 灵满分布 - 灵空分布(防/攻/射/机)
    ft = opp_model_obj._res_full_tot or 1.0
    lt = opp_model_obj._res_low_tot or 1.0
    res_diff = (np.asarray(opp_model_obj._res_full) / ft
                - np.asarray(opp_model_obj._res_low) / lt)
    # 卡组暴露3: B段14维的确定性压缩(能量3分组的均值)
    b = np.asarray(b_seg14, dtype=np.float64)
    cards3 = np.array([b[:5].mean(), b[5:10].mean(), b[10:].mean()])
    out = np.zeros(N_DIM, dtype=np.float32)
    out[:8] = np.clip(pca8, -4, 4)
    out[8] = np.clip(drift, 0, 2)
    out[9:13] = np.clip(res_diff, -1, 1)
    out[13:16] = np.clip(cards3, 0, 1)
    return out
