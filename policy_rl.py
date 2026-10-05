# -*- coding: utf-8 -*-
"""RL 策略: 与 BC 同结构的 MLP, 支持伯努利采样与 REINFORCE 更新。

- 输入: 40x30 灰度 x 3 帧堆叠(与 BC 一致, 可热启动);
- 输出: 9 键独立伯努利概率;
- 更新: REINFORCE(优势归一化) + 熵正则, Adam 梯度上升;
- 存取: 与 model_bc.npz 同格式(W1,b1,W2,b2), BCPolicy 可直接加载推理。
"""

import os

import numpy as np

KEY_ORDER = ["left", "right", "up", "down", "A", "B", "C", "D", "SC"]


class RLPolicy:
    GAMMA = 0.98        # 每决策步(100ms)折扣
    LR = 3e-5           # 小步长: 保护 BC 先验
    BETA_ENT = 0.005    # 熵正则系数
    GRAD_CLIP = 1.0

    def __init__(self, hidden=128, n_in=None, n_out=9, seed=0):
        self.n_in, self.hidden, self.n_out = n_in, hidden, n_out
        self.rng = np.random.default_rng(seed)
        self.W1 = self.b1 = self.W2 = self.b2 = None
        self._m = None
        self._v = None
        self._t = 0

    def load(self, path):
        d = np.load(path)
        self.W1, self.b1 = d["W1"], d["b1"]
        self.W2, self.b2 = d["W2"], d["b2"]
        self.n_in = self.W1.shape[0]
        self.hidden = self.W1.shape[1]
        self.n_out = self.W2.shape[1]
        self._m = [np.zeros_like(p) for p in self.params]
        self._v = [np.zeros_like(p) for p in self.params]
        return self

    def init(self, n_in):
        rng = np.random.default_rng(0)
        self.W1 = (rng.standard_normal((n_in, self.hidden)) / np.sqrt(n_in)).astype(np.float32)
        self.b1 = np.zeros(self.hidden, dtype=np.float32)
        self.W2 = (rng.standard_normal((self.hidden, self.n_out)) / np.sqrt(self.hidden)).astype(np.float32)
        self.b2 = np.zeros(self.n_out, dtype=np.float32)
        self.n_in = n_in
        self._m = [np.zeros_like(p) for p in self.params]
        self._v = [np.zeros_like(p) for p in self.params]
        return self

    @property
    def params(self):
        return [self.W1, self.b1, self.W2, self.b2]

    def forward(self, X):
        X = X.astype(np.float32) / 255.0
        H = np.maximum(0, X @ self.W1 + self.b1)
        Z = H @ self.W2 + self.b2
        P = 1.0 / (1.0 + np.exp(-Z))
        return H, P

    def sample(self, feat):
        """feat: 单帧堆叠特征 → 9 键伯努利采样动作(0/1)。"""
        _, P = self.forward(feat.reshape(1, -1))
        p = P[0]
        return (self.rng.random(self.n_out) < p).astype(np.float32)

    def update(self, feats, actions, rewards, baseline=None):
        """REINFORCE 批更新。feats: (N,D); actions: (N,9); rewards: 每决策步奖励。
        baseline: 跨局运行基线(推荐传入); None 时退化为局内均值。
        返回统计 dict。"""
        X = np.stack(feats).astype(np.float32)
        A = np.stack(actions).astype(np.float32)
        R = np.zeros(len(rewards), dtype=np.float32)
        acc = 0.0
        for i in range(len(rewards) - 1, -1, -1):
            acc = rewards[i] + self.GAMMA * acc
            R[i] = acc
        base = float(baseline) if baseline is not None else float(R.mean())
        adv = R - base
        sd = R.std()
        if sd > 1e-6:
            adv = adv / sd
        else:
            return {"skipped": True, "return": float(R.mean())}

        H, P = self.forward(X)
        Pc = np.clip(P, 1e-6, 1 - 1e-6)
        # logπ 梯度(伯努利): adv*(A-P); 熵正则: β*p*(1-p)*log((1-p)/p)
        dz = adv[:, None] * (A - P) + self.BETA_ENT * Pc * (1 - Pc) * np.log((1 - Pc) / Pc)
        dW2 = H.T @ dz
        db2 = dz.sum(0)
        dh = dz @ self.W2.T * (H > 0)
        Xf = X / 255.0
        dW1 = Xf.T @ dh
        db1 = dh.sum(0)
        grads = [dW1, db1, dW2, db2]

        gnorm = float(np.sqrt(sum(float((g * g).sum()) for g in grads)))
        if gnorm > self.GRAD_CLIP:
            scale = self.GRAD_CLIP / gnorm
            grads = [g * scale for g in grads]

        self._t += 1
        b1a, b2a, eps = 0.9, 0.999, 1e-8
        for i, g in enumerate(grads):
            self._m[i] = b1a * self._m[i] + (1 - b1a) * g
            self._v[i] = b2a * self._v[i] + (1 - b2a) * g * g
            mh = self._m[i] / (1 - b1a ** self._t)
            vh = self._v[i] / (1 - b2a ** self._t)
            self.params[i] += self.LR * mh / (np.sqrt(vh) + eps)   # 梯度上升

        ent = float((-Pc * np.log(Pc) - (1 - Pc) * np.log(1 - Pc)).mean())
        return {"skipped": False, "return": float(R.mean()),
                "grad_norm": gnorm, "entropy": ent}

    def save(self, path):
        np.savez(path, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2)
