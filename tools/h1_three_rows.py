# -*- coding: utf-8 -*-
"""H1 正式三行: MLP / GRU mem_v1 / Transformer(T=16) 同划分/种子/预算."""
import glob
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn

torch.set_num_threads(2)
EP = r'D:\temp\th123_models\**\ep_*.npz'
OUT = r'D:\temp\scratch\h1_three_rows.json'
SEED = 0
T = 16


def load():
    raw = []
    for p in glob.glob(EP, recursive=True):
        try:
            with np.load(p, allow_pickle=True) as z:
                S = np.asarray(z['sides'], np.float32)
                A = np.asarray(z['acts'], np.int64)
            if len(A) < 20:
                continue
            raw.append((S, A, p))
        except Exception:
            continue
    if not raw:
        return []
    dims = {}
    for S, A, p in raw:
        dims[S.shape[1]] = dims.get(S.shape[1], 0) + 1
    D = max(dims, key=dims.get)
    kept = [(S, A) for S, A, p in raw if S.shape[1] == D]
    print('[three] episodes=%d dims=%s use D=%d kept=%d'
          % (len(raw), dims, D, len(kept)))
    return kept


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
        return self.o(h[:, -1])


class TT(nn.Module):
    def __init__(self, d, n, h=64):
        super().__init__()
        self.proj = nn.Linear(d, h)
        self.pos = nn.Parameter(torch.zeros(1, T, h))
        enc = nn.TransformerEncoderLayer(h, 4, 2 * h, batch_first=True,
                                         dropout=0.1, activation='gelu')
        self.tr = nn.TransformerEncoder(enc, 2,
                                        enable_nested_tensor=False)
        self.out = nn.Linear(h, n)

    def forward(self, x):
        z = self.proj(x) + self.pos[:, :x.shape[1]]
        mask = torch.triu(torch.ones(x.shape[1], x.shape[1],
                                     dtype=torch.bool), 1)
        return self.out(self.tr(z, mask=mask)[:, -1])


def main():
    eps = load()
    if len(eps) < 4:
        print(json.dumps({'error': 'episodes too few %d' % len(eps)}))
        return 1
    rng = np.random.RandomState(SEED)
    idx = np.arange(len(eps))
    rng.shuffle(idx)
    nval = max(1, len(eps) // 5)
    tr = [eps[i] for i in idx[:-nval]]
    va = [eps[i] for i in idx[-nval:]]
    D = eps[0][0].shape[1]
    n = int(max(int(a.max()) for _, a in eps)) + 1
    Xtr = np.concatenate([s for s, _ in tr])
    Ytr = np.concatenate([a for _, a in tr])
    Xva = np.concatenate([s for s, _ in va])
    Yva = np.concatenate([a for _, a in va])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xtr = (Xtr - mu) / sd
    Xva = (Xva - mu) / sd
    res = {'seed': SEED, 'T': T, 'episodes': len(eps),
           'train_steps': len(Ytr), 'val_steps': len(Yva), 'n_macros': n}
    # MLP
    m = MLP(D, n)
    opt = torch.optim.Adam(m.parameters(), 1e-3)
    xt, yt = torch.tensor(Xtr), torch.tensor(Ytr)
    for _ in range(30):
        opt.zero_grad()
        nn.functional.cross_entropy(m(xt), yt).backward()
        opt.step()
    with torch.no_grad():
        res['mlp_top1'] = round(float(
            (m(torch.tensor(Xva)).argmax(1).numpy() == Yva).mean()), 3)
    # windowed sets
    xs, ys = [], []
    for i in range(T, len(Xtr)):
        xs.append(Xtr[i - T:i])
        ys.append(Ytr[i])
    xv, yv = [], []
    for i in range(T, len(Xva)):
        xv.append(Xva[i - T:i])
        yv.append(Yva[i])
    xs = np.stack(xs)[:4000]
    ys = np.array(ys)[:4000]
    xv = np.stack(xv)
    yv = np.array(yv)
    res['windows'] = {'train': len(xs), 'val': len(xv)}
    xt = torch.tensor(xs)
    yt = torch.tensor(ys)
    # GRU
    g = GRU(D, n)
    opt = torch.optim.Adam(g.parameters(), 1e-3)
    for _ in range(30):
        opt.zero_grad()
        nn.functional.cross_entropy(g(xt), yt).backward()
        opt.step()
    with torch.no_grad():
        res['gru_top1'] = round(float(
            (g(torch.tensor(xv)).argmax(1).numpy() == yv).mean()), 3)
    # Transformer
    tt = TT(D, n)
    opt = torch.optim.Adam(tt.parameters(), 1e-3)
    for _ in range(30):
        opt.zero_grad()
        nn.functional.cross_entropy(tt(xt), yt).backward()
        opt.step()
    with torch.no_grad():
        res['transformer_top1'] = round(float(
            (tt(torch.tensor(xv)).argmax(1).numpy() == yv).mean()), 3)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
