# -*- coding: utf-8 -*-
"""损失函数：类平衡 + 标签平滑 + 多任务。

为什么必须做类平衡：
  实测标签分布极度不均衡 —— reimu 最大类 14353 行、最小类 3 行（imbalance 4784:1），
  marisa 16463:24，suika 30548:12。直接 CE 会让模型塌缩到"高频宏"，
  而低频宏里恰恰包含符卡/连段这类高价值动作。
  对策：权重 = (1/count)^power，power=0.5（inverse-sqrt）为默认，
  比完全 inverse-frequency 温和，避免把 3 样本的类权重抬到 5000 倍。
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


def make_class_weights(counts: np.ndarray, power: float = 0.5, clip: float = 20.0) -> np.ndarray:
    """返回归一化到均值 1 的类权重。counts 为训练集各类计数（含 0）。"""
    counts = np.asarray(counts, dtype=np.float64)
    w = np.zeros_like(counts)
    nz = counts > 0
    w[nz] = (1.0 / counts[nz]) ** float(power)
    if nz.any():
        w[nz] = np.minimum(w[nz], float(clip))
        w[nz] = w[nz] / w[nz].mean()
    return w.astype(np.float32)


class MacroLoss(nn.Module):
    """策略 CE（类平衡 + 标签平滑）+ 可选下一拍辅助 CE + 可选价值 MSE。"""

    def __init__(
        self,
        class_weights: np.ndarray | None = None,
        label_smoothing: float = 0.05,
        aux_weight: float = 0.2,
        value_weight: float = 0.0,
        ignore_index: int = -100,
    ):
        super().__init__()
        w = None if class_weights is None else torch.as_tensor(class_weights, dtype=torch.float32)
        self.register_buffer("class_weights", w if w is not None else torch.empty(0))
        self.label_smoothing = float(label_smoothing)
        self.aux_weight = float(aux_weight)
        self.value_weight = float(value_weight)
        self.ignore_index = int(ignore_index)

    def policy_ce(self, logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        w = self.class_weights if self.class_weights.numel() > 0 else None
        return F.cross_entropy(
            logits, y, weight=w, label_smoothing=self.label_smoothing,
            ignore_index=self.ignore_index,
        )

    def forward(self, out: dict, batch: dict) -> dict[str, torch.Tensor]:
        losses: dict[str, torch.Tensor] = {}
        losses["policy"] = self.policy_ce(out["logits"], batch["y"])
        total = losses["policy"]

        if "next_logits" in out and "next_y" in batch:
            aux = self.policy_ce(out["next_logits"], batch["next_y"])
            losses["next_macro"] = aux
            total = total + self.aux_weight * aux

        if "value" in out and "outcome" in batch and self.value_weight > 0:
            target = (batch["outcome"].float() > 0).float()
            v = F.binary_cross_entropy_with_logits(out["value"], target)
            losses["value"] = v
            total = total + self.value_weight * v

        losses["total"] = total
        return losses


def soft_cross_entropy(logits: torch.Tensor, target_probs: torch.Tensor) -> torch.Tensor:
    """软标签 CE（用于把 teacher 的分布蒸馏进学生；标准 KD）。"""
    logp = F.log_softmax(logits, dim=-1)
    return -(target_probs * logp).sum(dim=-1).mean()


__all__ = ["make_class_weights", "MacroLoss", "soft_cross_entropy"]
