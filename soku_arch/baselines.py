# -*- coding: utf-8 -*-
"""无依赖基线：多数类 + 多项逻辑回归（纯 NumPy，Adam）。

为什么必须给基线：
  前序项目从不报基线，只报自己的准确率，导致"模型到底学到了什么"无法判断。
  在 4784:1 的类别不均衡 + 标签熵仅 3.4（上限 ln55≈4.0）的数据上，
  "多数类"本身就能拿到不低的准确率 —— 不报基线等于自欺。
"""
from __future__ import annotations

import numpy as np


def majority_logits(y_train: np.ndarray, n_val: int, n_classes: int) -> np.ndarray:
    """把训练集众数类作为唯一预测（logits 用 one-hot，便于走同一套指标）。"""
    counts = np.bincount(np.asarray(y_train), minlength=n_classes)
    logits = np.zeros((n_val, n_classes), dtype=np.float64)
    logits[:, int(counts.argmax())] = 1.0
    return logits


def logreg_logits(
    Xtr: np.ndarray, ytr: np.ndarray, Xva: np.ndarray, n_classes: int,
    epochs: int = 300, lr: float = 0.05, l2: float = 1e-4, seed: int = 0,
    class_weights: np.ndarray | None = None, batch: int = 2048,
) -> np.ndarray:
    """多项逻辑回归，Adam 优化。返回验证集 logits。

    这是"线性可及上限"的参考：若深度模型赢不过它，说明特征里没有非线性可利用的结构。
    """
    rng = np.random.default_rng(seed)
    Xtr = np.asarray(Xtr, dtype=np.float32)
    Xva = np.asarray(Xva, dtype=np.float32)
    ytr = np.asarray(ytr, dtype=np.int64)
    n, d = Xtr.shape
    W = np.zeros((d, n_classes), dtype=np.float32)
    b = np.zeros(n_classes, dtype=np.float32)
    mW = np.zeros_like(W); vW = np.zeros_like(W)
    mb = np.zeros_like(b); vb = np.zeros_like(b)
    w = np.ones(n_classes, dtype=np.float32) if class_weights is None else class_weights.astype(np.float32)
    b1, b2, eps = 0.9, 0.999, 1e-8

    for ep in range(epochs):
        perm = rng.permutation(n)
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            x = Xtr[idx]
            y = ytr[idx]
            z = x @ W + b
            z = z - z.max(axis=1, keepdims=True)
            e = np.exp(z)
            p = e / e.sum(axis=1, keepdims=True)
            sample_w = w[y]
            dz = p
            dz[np.arange(len(y)), y] -= 1.0
            dz *= sample_w[:, None]
            dz /= len(y)
            gW = x.T @ dz + l2 * W
            gb = dz.sum(axis=0)
            for (pm, pv, g, par) in ((mW, vW, gW, W), (mb, vb, gb, b)):
                pm *= b1; pm += (1 - b1) * g
                pv *= b2; pv += (1 - b2) * g * g
                mh = pm / (1 - b1 ** (ep + 1))
                vh = pv / (1 - b2 ** (ep + 1))
                par -= lr * mh / (np.sqrt(vh) + eps)
    return (Xva @ W + b).astype(np.float64)


__all__ = ["majority_logits", "logreg_logits"]
