# -*- coding: utf-8 -*-
"""评估指标：宏选择任务 + 校准 + 分布覆盖。

为什么不用单一 top-1 准确率：
  * 类别极不均衡（4784:1），top-1 会被高频类支配 -> 必须同时看 macro-F1 与各类召回；
  * 策略网络的置信度会直接用于探索/门控（前序项目用 logit 做门步判定），
    -> 必须看校准（ECE）；
  * "模型学到了什么策略"看分布：与 teacher 的 JS 散度 + 覆盖了多少宏。
"""
from __future__ import annotations

import numpy as np


def top_k_accuracy(logits: np.ndarray, y: np.ndarray, k: int = 1) -> float:
    logits = np.asarray(logits, dtype=np.float64)
    y = np.asarray(y)
    if k <= 1:
        return float((logits.argmax(axis=1) == y).mean())
    k = min(k, logits.shape[1])
    topk = np.argpartition(-logits, k - 1, axis=1)[:, :k]
    return float((topk == y[:, None]).any(axis=1).mean())


def confusion(logits: np.ndarray, y: np.ndarray, n_classes: int) -> np.ndarray:
    pred = np.asarray(logits).argmax(axis=1)
    cm = np.zeros((n_classes, n_classes), dtype=np.int64)
    np.add.at(cm, (np.asarray(y), pred), 1)
    return cm


def per_class_recall(logits: np.ndarray, y: np.ndarray, n_classes: int) -> np.ndarray:
    cm = confusion(logits, y, n_classes)
    support = cm.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rec = np.where(support > 0, np.diag(cm) / np.maximum(support, 1), np.nan)
    return rec


def macro_f1(logits: np.ndarray, y: np.ndarray, n_classes: int) -> float:
    cm = confusion(logits, y, n_classes)
    tp = np.diag(cm).astype(np.float64)
    fp = cm.sum(axis=0) - tp
    fn = cm.sum(axis=1) - tp
    denom = 2 * tp + fp + fn
    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.where(denom > 0, 2 * tp / np.maximum(denom, 1), np.nan)
    present = cm.sum(axis=1) > 0
    return float(np.nanmean(f1[present])) if present.any() else float("nan")


def softmax(logits: np.ndarray) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def ece(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> float:
    """多分类 top-1 置信度的期望校准误差。"""
    probs = np.asarray(probs, dtype=np.float64)
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == np.asarray(y)).astype(np.float64)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(conf, bins) - 1, 0, n_bins - 1)
    total = len(conf)
    out = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            out += (m.sum() / total) * abs(correct[m].mean() - conf[m].mean())
    return float(out)


def js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """两个离散分布（未归一化也可）的 Jensen-Shannon 散度，以 2 为底 -> [0,1]。"""
    p = np.asarray(p, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    p = p / max(p.sum(), 1e-12)
    q = q / max(q.sum(), 1e-12)
    m = 0.5 * (p + q)

    def kl(a, b):
        mask = a > 0
        return float((a[mask] * np.log2(a[mask] / np.maximum(b[mask], 1e-12))).sum())

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def coverage(logits: np.ndarray, n_classes: int, min_share: float = 1e-4) -> dict:
    """模型实际会选的宏集合规模：区分"只在少数宏上打转"与"用满宏库"。"""
    pred = np.asarray(logits).argmax(axis=1)
    counts = np.bincount(pred, minlength=n_classes).astype(np.float64)
    share = counts / max(counts.sum(), 1)
    return {
        "n_predicted_classes": int((counts > 0).sum()),
        "n_classes_above_min_share": int((share >= min_share).sum()),
        "top1_share": float(share.max()),
        "entropy": float(-(share[share > 0] * np.log(share[share > 0])).sum()),
        "uniform_entropy": float(np.log(n_classes)),
    }


def summarize(logits: np.ndarray, y: np.ndarray, n_classes: int) -> dict:
    probs = softmax(logits)
    rec = per_class_recall(logits, y, n_classes)
    present = ~np.isnan(rec)
    return {
        "n": int(len(y)),
        "top1": top_k_accuracy(logits, y, 1),
        "top5": top_k_accuracy(logits, y, 5),
        "top10": top_k_accuracy(logits, y, 10),
        "macro_f1": macro_f1(logits, y, n_classes),
        "mean_recall_present_classes": float(np.nanmean(rec[present])) if present.any() else float("nan"),
        "n_classes_present": int(present.sum()),
        "n_classes_hit": int(np.nansum(rec[present] > 0) if present.any() else 0),
        "ece_15bin": ece(probs, y, 15),
        "pred_coverage": coverage(logits, n_classes),
    }


__all__ = [
    "top_k_accuracy", "confusion", "per_class_recall", "macro_f1", "softmax",
    "ece", "js_divergence", "coverage", "summarize",
]
