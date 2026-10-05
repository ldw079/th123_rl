# -*- coding: utf-8 -*-
"""M1: 世界动力学模型 — s' = f(s, my_macro) 的numpy MLP。

输入25维(24物理状态+1宏ID) → 输出24维(下一拍物理状态)。
纯numpy实现(工程无依赖纪律), Adam优化, 批训练。
用途: M2隐状态特征 → M3 Dreamer-lite想象训练。
"""
import os

import numpy as np

STATE_DIM = 24   # 物理状态(不含宏ID)
INPUT_DIM = 25   # 状态+宏ID
HIDDEN = 128


class DynamicsModel:
    def __init__(self, path=None):
        self.path = path
        rng = np.random.default_rng(42)
        self.W1 = (rng.standard_normal((INPUT_DIM, HIDDEN)) / np.sqrt(INPUT_DIM)).astype(np.float32)
        self.b1 = np.zeros(HIDDEN, dtype=np.float32)
        self.W2 = (rng.standard_normal((HIDDEN, HIDDEN)) / np.sqrt(HIDDEN)).astype(np.float32)
        self.b2 = np.zeros(HIDDEN, dtype=np.float32)
        self.W3 = (rng.standard_normal((HIDDEN, STATE_DIM)) / np.sqrt(HIDDEN)).astype(np.float32)
        self.b3 = np.zeros(STATE_DIM, dtype=np.float32)
        self._m = {k: np.zeros_like(v) for k, v in self._params().items()}
        self._v = {k: np.zeros_like(v) for k, v in self._params().items()}
        self._t = 0
        if path and os.path.exists(path):
            self.load(path)

    def _params(self):
        return {"W1": self.W1, "b1": self.b1, "W2": self.W2,
                "b2": self.b2, "W3": self.W3, "b3": self.b3}

    def forward(self, X):
        h1 = np.maximum(0, X @ self.W1 + self.b1)
        h2 = np.maximum(0, h1 @ self.W2 + self.b2)
        return h2 @ self.W3 + self.b3, h1, h2   # 输出+隐层(隐状态特征用)

    def hidden(self, X):
        """只取隐层(M2特征提取用)。"""
        _, h1, h2 = self.forward(X)
        return np.concatenate([h1, h2], axis=-1)   # 256维

    def train(self, X, Y, epochs=30, lr=1e-3, batch=256, verbose=True):
        n = len(X)
        for ep in range(epochs):
            idx = np.random.permutation(n)
            total_loss = 0.0
            for i in range(0, n, batch):
                bi = idx[i:i + batch]
                xb, yb = X[bi], Y[bi]
                pred, h1, h2 = self.forward(xb)
                diff = pred - yb
                loss = float(np.mean(diff * diff))
                total_loss += loss * len(bi)
                # 反向传播
                dp = 2 * diff / len(bi)
                dW3 = h2.T @ dp
                db3 = dp.sum(axis=0)
                dh2 = dp @ self.W3.T
                dh2 = dh2 * (h2 > 0)
                dW2 = h1.T @ dh2
                db2 = dh2.sum(axis=0)
                dh1 = dh2 @ self.W2.T
                dh1 = dh1 * (h1 > 0)
                dW1 = xb.T @ dh1
                db1 = dh1.sum(axis=0)
                # Adam
                self._t += 1
                bc1 = 1 - 0.9 ** self._t
                bc2 = 1 - 0.999 ** self._t
                for k, g in (("W1", dW1), ("b1", db1), ("W2", dW2),
                             ("b2", db2), ("W3", dW3), ("b3", db3)):
                    p = getattr(self, k)
                    self._m[k] = 0.9 * self._m[k] + 0.1 * g
                    self._v[k] = 0.999 * self._v[k] + 0.001 * g * g
                    setattr(self, k, p - lr * (self._m[k] / bc1)
                            / (np.sqrt(self._v[k] / bc2) + 1e-8))
            if verbose and (ep + 1) % 10 == 0:
                print("  epoch %d: MSE %.6f" % (ep + 1, total_loss / n))

    def save(self, path):
        np.savez(path, **self._params())

    def load(self, path):
        d = np.load(path)
        for k in self._params():
            setattr(self, k, d[k])


def build_training_data(files):
    """从转移日志构建(s,a)→s'对。连续行配对, 跳过回合边界(HP回满)。"""
    all_rows = []
    for f in files:
        if os.path.exists(f):
            d = np.load(f)
            all_rows.append(d["T"])
    if not all_rows:
        return None, None
    rows = np.concatenate(all_rows, axis=0)
    n = len(rows)
    X, Y = [], []
    for i in range(n - 1):
        # 回合边界: HP从低回满 → 不配对
        if rows[i][8] < 0.9 and rows[i + 1][8] > 0.99:
            continue
        if rows[i][9] < 0.9 and rows[i + 1][9] > 0.99:
            continue
        X.append(rows[i])          # 25维: 状态+宏
        Y.append(rows[i + 1][:24]) # 24维: 下一拍状态
    return np.asarray(X, dtype=np.float32), np.asarray(Y, dtype=np.float32)
