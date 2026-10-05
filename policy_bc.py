# -*- coding: utf-8 -*-
"""行为克隆策略: 小 MLP(纯 numpy), 输入 40x30 灰度帧, 输出 9 键按下概率。"""

import os

import numpy as np

import config

KEY_ORDER = ["left", "right", "up", "down", "A", "B", "C", "D", "SC"]

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_bc.npz")


def make_mlp(n_in, hidden, n_out, seed=0):
    rng = np.random.default_rng(seed)
    W1 = rng.standard_normal((n_in, hidden)).astype(np.float32) / np.sqrt(n_in)
    b1 = np.zeros(hidden, dtype=np.float32)
    W2 = rng.standard_normal((hidden, n_out)).astype(np.float32) / np.sqrt(hidden)
    b2 = np.zeros(n_out, dtype=np.float32)
    return W1, b1, W2, b2


class BCPolicy:
    def __init__(self, path=MODEL_PATH, thresh=None):
        self.path = path
        self.thresh = thresh or config.BC_THRESH
        self._held = [False] * len(KEY_ORDER)   # 滞回状态, 防输出抖动

    def load(self):
        d = np.load(self.path)
        self.W1, self.b1 = d["W1"], d["b1"]
        self.W2, self.b2 = d["W2"], d["b2"]
        return self

    def forward(self, x):
        x = x.astype(np.float32) / 255.0
        h = np.maximum(0, x @ self.W1 + self.b1)
        y = 1.0 / (1.0 + np.exp(-(h @ self.W2 + self.b2)))
        return y

    def predict(self, feat):
        """feat: 堆叠特征向量 → 按下的键名列表(带滞回: 0.6 按下, 0.4 松开)。"""
        p = self.forward(feat.reshape(1, -1))[0]
        for i in range(len(p)):
            if p[i] > 0.6:
                self._held[i] = True
            elif p[i] < 0.4:
                self._held[i] = False
        # 方向互斥: 左右/上下同时按住时只保留概率高的一侧(专家数据里从不同时按)
        for a, b in ((0, 1), (2, 3)):
            if self._held[a] and self._held[b]:
                if p[a] >= p[b]:
                    self._held[b] = False
                else:
                    self._held[a] = False
        return [name for i, name in enumerate(KEY_ORDER) if self._held[i]]

    def sample(self, feat):
        """按模型概率伯努利采样 → 键名列表。
        RL 训练时的真实行为分布就是采样——评估 RL 策略用这个才公平。"""
        p = self.forward(feat.reshape(1, -1))[0]
        return [name for i, name in enumerate(KEY_ORDER)
                if np.random.random() < p[i]]
