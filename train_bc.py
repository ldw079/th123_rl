# -*- coding: utf-8 -*-
"""行为克隆训练: 读 data/bc_run_* 样本(loop.py --record 录制), 训练 numpy MLP, 存 model_bc.npz。

运行: <python> train_bc.py
"""

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from policy_bc import KEY_ORDER, make_mlp

HIDDEN = 128
EPOCHS = 20
BATCH = 64
LR = 1e-3


def load_data():
    dirs = sorted(glob.glob(os.path.join(config.DATA_DIR, "bc_run_*")))
    xs, ys = [], []
    for d in dirs:
        f, a = os.path.join(d, "frames.npy"), os.path.join(d, "actions.npy")
        if os.path.exists(f) and os.path.exists(a):
            xs.append(np.load(f))
            ys.append(np.load(a))
    if not xs:
        print("[错误] data/ 下没有 bc_run_* 样本, 先用 loop.py --record 录一些")
        sys.exit(1)
    X = np.concatenate(xs)
    Y = np.concatenate(ys)
    dist = {k: int(Y[:, i].sum()) for i, k in enumerate(KEY_ORDER)}
    print("[数据] %d 个样本, 按键分布: %s" % (len(X), dist))
    # R38(第九轮审计§2.2): 返回会话长度 — 切分须按录制会话分块,
    # 全局乱序会让相邻近重复帧跨train/test(验证精度虚高)
    return X, Y, [len(x) for x in xs]


def train():
    X, Y, sess_lens = load_data()
    rng = np.random.default_rng(20261003)   # R38: 固定种子可复现
    sess_perm = rng.permutation(len(sess_lens))
    n_tr_sess = max(1, int(len(sess_lens) * 0.85))
    tr_sess = set(sess_perm[:n_tr_sess].tolist())
    tr_mask = np.zeros(len(X), dtype=bool)
    b = 0
    for k, L in enumerate(sess_lens):
        if k in tr_sess:
            tr_mask[b:b + L] = True
        b += L
    Xtr, Ytr = X[tr_mask], Y[tr_mask]
    Xte, Yte = X[~tr_mask], Y[~tr_mask]
    if len(Xte) == 0:      # 单会话退化: 至少留5%尾部
        cut = int(len(X) * 0.95)
        Xtr, Ytr, Xte, Yte = X[:cut], Y[:cut], X[cut:], Y[cut:]
    print("[切分] 会话块: 训练%d条 / 验证%d条" % (len(Xtr), len(Xte)))
    n_in = X.shape[1]
    W1, b1, W2, b2 = make_mlp(n_in, HIDDEN, len(KEY_ORDER))
    params = [W1, b1, W2, b2]
    ms = [np.zeros_like(p) for p in params]
    vs = [np.zeros_like(p) for p in params]
    Xf = Xtr.astype(np.float32) / 255.0
    nt = len(Xtr)
    beta1, beta2, eps = 0.9, 0.999, 1e-8

    # 按类别频率平衡权重: 修正"什么都不按"与"只按左"这类统计最优但行为塌缩的解
    p_rate = Ytr.mean(axis=0)
    w_pos = (1.0 / (2.0 * np.clip(p_rate, 1e-3, None))).astype(np.float32)
    w_neg = (1.0 / (2.0 * np.clip(1.0 - p_rate, 1e-3, None))).astype(np.float32)

    for epoch in range(EPOCHS):
        perm_t = np.random.permutation(nt)
        total = 0.0
        steps = 0
        for i in range(0, nt, BATCH):
            idx = perm_t[i:i + BATCH]
            x = Xf[idx]
            y = Ytr[idx].astype(np.float32)
            h = np.maximum(0, x @ W1 + b1)
            p = 1.0 / (1.0 + np.exp(-(h @ W2 + b2)))
            loss = -np.mean(w_pos * y * np.log(p + 1e-7) + w_neg * (1 - y) * np.log(1 - p + 1e-7))
            total += loss * len(idx)
            steps += len(idx)

            # dL/dz = p*(w_neg + (w_pos - w_neg)*y) - w_pos*y
            dz = (p * (w_neg + (w_pos - w_neg) * y) - w_pos * y) / len(idx)
            dW2 = h.T @ dz
            db2 = dz.sum(0)
            dh = dz @ W2.T * (h > 0)
            dW1 = x.T @ dh
            db1 = dh.sum(0)

            for pi, g in enumerate((dW1, db1, dW2, db2)):
                ms[pi] = beta1 * ms[pi] + (1 - beta1) * g
                vs[pi] = beta2 * vs[pi] + (1 - beta2) * g * g
                mh = ms[pi] / (1 - beta1 ** (epoch + 1))
                vh = vs[pi] / (1 - beta2 ** (epoch + 1))
                params[pi] -= LR * mh / (np.sqrt(vh) + eps)

        def acc_of(Xf_, Y_):
            h_ = np.maximum(0, Xf_ @ W1 + b1)
            p_ = 1.0 / (1.0 + np.exp(-(h_ @ W2 + b2)))
            return float(((p_ > 0.5) == (Y_ > 0.5)).mean())

        def per_key_acc(Xf_, Y_):
            h_ = np.maximum(0, Xf_ @ W1 + b1)
            p_ = 1.0 / (1.0 + np.exp(-(h_ @ W2 + b2)))
            return {k: float(((p_[:, i] > 0.5) == (Y_[:, i] > 0.5)).mean())
                    for i, k in enumerate(KEY_ORDER)}

        if (epoch + 1) % 5 == 0 or epoch == 0:
            pk = per_key_acc(Xte.astype(np.float32) / 255.0, Yte)
            print("epoch %2d: loss=%.4f 训练acc=%.3f 验证acc=%.3f" % (epoch + 1, total / steps,
                  acc_of(Xf, Ytr), acc_of(Xte.astype(np.float32) / 255.0, Yte)))
            print("        验证分键acc: %s" % {k: round(v, 3) for k, v in pk.items()})

    np.savez("model_bc.npz", W1=W1, b1=b1, W2=W2, b2=b2)
    print("[完成] 已保存 model_bc.npz (BOT_MODE=bc 可用)")


if __name__ == "__main__":
    train()
