# -*- coding: utf-8 -*-
"""H1 对照协议 demo: episodes held-out next-macro top1 (MLP无历史 vs GRU mem_v1 代理)."""
import glob
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn

EP = r'D:\temp\th123_models\fleet\episodes\*.npz'
OUT = r'D:\temp\scratch\h1_mem_compare_20261026.json'
torch.set_num_threads(2)


def load():
    eps = []
    for p in sorted(glob.glob(EP), key=os.path.getmtime):
        try:
            with np.load(p, allow_pickle=True) as z:
                S = np.asarray(z['sides'], np.float32)
                A = np.asarray(z['acts'], np.int64)
            if len(A) < 20:
                continue
            eps.append((S, A))
        except Exception:
            continue
    return eps


class MLP(nn.Module):
    def __init__(self, d, n):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, 128), nn.ReLU(),
                                 nn.Linear(128, n))

    def forward(self, x):
        return self.net(x)


class GRU(nn.Module):
    def __init__(self, d, n, h=64):
        super().__init__()
        self.g = nn.GRU(d, h, batch_first=True)
        self.o = nn.Linear(h, n)

    def forward(self, x):
        h, _ = self.g(x)
        return self.o(h)


def run(eps):
    if len(eps) < 2:
        return {'error': 'need >=2 episodes, got %d' % len(eps)}
    rng = np.random.RandomState(0)
    idx = np.arange(len(eps))
    rng.shuffle(idx)
    tr = [eps[i] for i in idx[:max(1, len(eps) - 1)]]
    va = [eps[i] for i in idx[max(1, len(eps) - 1):]]
    D = eps[0][0].shape[1]
    n = int(max(int(a.max()) for _, a in eps)) + 1
    Xtr = np.concatenate([s for s, _ in tr])
    Ytr = np.concatenate([a for _, a in tr])
    Xva = np.concatenate([s for s, _ in va])
    Yva = np.concatenate([a for _, a in va])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xtr = (Xtr - mu) / sd
    Xva = (Xva - mu) / sd
    res = {'episodes': len(eps), 'train_steps': len(Ytr),
           'val_steps': len(Yva), 'n_macros': n}
    # MLP
    m = MLP(D, n)
    opt = torch.optim.Adam(m.parameters(), 1e-3)
    xt, yt = torch.tensor(Xtr), torch.tensor(Ytr)
    for _ in range(100):
        opt.zero_grad()
        loss = nn.functional.cross_entropy(m(xt), yt)
        loss.backward()
        opt.step()
    with torch.no_grad():
        pr = m(torch.tensor(Xva)).argmax(1).numpy()
    res['mlp_top1'] = round(float((pr == Yva).mean()), 3)
    # GRU mem_v1 代理 (全序列)
    Xs = torch.tensor(Xtr[None])
    ys = torch.tensor(Ytr[None])
    g = GRU(D, n)
    opt = torch.optim.Adam(g.parameters(), 1e-3)
    for _ in range(30):
        opt.zero_grad()
        out = g(Xs)
        loss = nn.functional.cross_entropy(out.reshape(-1, n), ys.reshape(-1))
        loss.backward()
        opt.step()
    with torch.no_grad():
        pr = g(torch.tensor(Xva[None])).argmax(2).numpy().reshape(-1)
    res['gru_top1'] = round(float((pr == Yva).mean()), 3)
    res['note'] = ('协议 demo；仅 %d episodes，数字不具统计意义，'
                   '待数据量足够后正式 A/B' % len(eps))
    return res


def main():
    eps = load()
    res = run(eps)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
