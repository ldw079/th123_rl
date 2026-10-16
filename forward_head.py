# -*- coding: utf-8 -*-
"""CE-4(方案§可执行方案): 一步位置前向头 — 预测下一决策点位置特征。

目标: 预测4维 (adx', own_corner', opp_corner', air') —
  监督信号 = 训练rollout的下一拍状态(零采集成本)。
实现: ppo.py加Wf头(trunk+side → 隐32 → 4维), MSE损失,
  λ_fwd=0.05起步(与aux头同量级)。
用途: a)辅助损失(表征编码位置动力学) b)CE-5反事实探测的模型化预测器。

本模块 = 纯设计件(未接线; CE-4方案要求双实现等价后才接入训练)。

numpy版前向 + 梯度计算; GPU版在ppo_gpu.py另行实现(同R54纪律)。
"""
from __future__ import annotations

import numpy as np

# 前向头维度(方案定稿)
FWD_DIMS = 4
FWD_HIDDEN = 32
LAMBDA_FWD = 0.05     # 辅助损失系数(起步值, 与aux同量级)


def fwd_targets(s_next_core):
    """从下一拍core特征提取4维目标。

    需在feat_builder.build(s')返回后调用, 提取:
      [0] adx: clip(adx/600,0,1) — 段1标量[4]
      [1] own_corner: 我方贴角 — 段9卡牌区[150](值1.5→/1.5归一)
      [2] opp_corner: 对手贴角 — 段9卡牌区[149]
      [3] air: 我方滞空 — 段1标量[10]

    R138(2026-10-15晚)修正: 原索引用[34]/[40]/[1] — 实为段4位置带
    one-hot/对手灵力, 四目标全成常数(测试自造fictional core通过=
    R133 trunk=128同型错误)。索引经真实FeatureBuilder实证
    (贴角翻转/adx线性/air翻转), 段偏移账: 1:16+2:16+3:2+4:14+5:4
    +6:6+7:36+8:36 → 段9起于130, 贴角位=130+19/130+20。
    """
    return np.array([
        float(s_next_core[4]),
        float(s_next_core[150]) / 1.5,
        float(s_next_core[149]) / 1.5,
        float(s_next_core[10]),
    ], dtype=np.float32)


class ForwardHead:
    """CE-4 前向头(numpy版) — trunk+side → 隐32 → 4维。

    权重命名 Wf1/bf1/Wf2/bf2 (与W1v/b1v命名风格一致)。
    save/load键: Wf1, bf1, Wf2, bf2。
    """

    def __init__(self, trunk_flat, n_side, rng=None):
        rng = rng or np.random.default_rng(9)
        s1 = 1.0 / np.sqrt(trunk_flat + n_side)
        self.Wf1 = (rng.standard_normal((trunk_flat + n_side, FWD_HIDDEN))
                    * s1).astype(np.float32)
        self.bf1 = np.zeros(FWD_HIDDEN, dtype=np.float32)
        s2 = 1.0 / np.sqrt(FWD_HIDDEN)
        self.Wf2 = (rng.standard_normal((FWD_HIDDEN, FWD_DIMS))
                    * s2 * 0.01).astype(np.float32)  # 小初始化
        self.bf2 = np.zeros(FWD_DIMS, dtype=np.float32)

    def forward(self, Xn, S):
        """(B, trunk_flat) + (B, n_side) → (B, 4)。"""
        inp = np.concatenate([Xn, S], axis=1)
        h = np.maximum(0, inp @ self.Wf1 + self.bf1)
        return h @ self.Wf2 + self.bf2, h

    def loss_and_grads(self, Xn, S, targets):
        """MSE损失 + 梯度(手动反向传播)。

        返回 (loss, dXn, dS, grads_dict)。
        """
        inp = np.concatenate([Xn, S], axis=1)
        h = np.maximum(0, inp @ self.Wf1 + self.bf1)
        pred = h @ self.Wf2 + self.bf2
        diff = pred - targets
        loss = float((diff ** 2).mean())

        # 反向
        dpred = 2.0 * diff / diff.size          # (B, 4) — .size=B*4(MSE mean)
        dWf2 = h.T @ dpred                      # (32, 4)
        dbf2 = dpred.sum(axis=0)
        dh = dpred @ self.Wf2.T                # (B, 32)
        dh[h <= 0] = 0
        dWf1 = inp.T @ dh                       # (trunk+side, 32)
        dbf1 = dh.sum(axis=0)
        dinp = dh @ self.Wf1.T                  # (B, trunk+side)
        dXn = dinp[:, :Xn.shape[1]]
        dS = dinp[:, Xn.shape[1]:]
        grads = {'Wf1': dWf1, 'bf1': dbf1, 'Wf2': dWf2, 'bf2': dbf2}
        return loss, dXn, dS, grads
