# -*- coding: utf-8 -*-
"""H1 demo 第三行: 小 Transformer(T=16) next-macro top1 (协议 demo)."""
import glob
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn

torch.set_num_threads(2)
EP = r'D:\temp\th123_models\**\ep_*.npz'
OUT = r'D:\temp\scratch\h1_transformer_demo.json'


def load():
    raw = []
    for p in glob.glob(EP, recursive=True):
        try:
            with np.load(p, allow_pickle=True) as z:
                S = np.asarray(z['sides'], np.float32)
                A = np.asarray(z['acts'], np.int64)
            if len(A) < 20:
                continue
            raw.append((S, A))
        except Exception:
            continue
    if not raw:
        return []
    dims = {}
    for S, A in raw:
        dims[S.shape[1]] = dims.get(S.shape[1], 0) + 1
    D = max(dims, key=dims.get)
    return [(S, A) for S, A in raw if S.shape[1] == D]


class TT(nn.Module):
    def __init__(self, d, n, T=16, h=64, layers=2):
        super().__init__()
        self.proj = nn.Linear(d, h)
        self.pos = nn.Parameter(torch.zeros(1, T, h))
        enc = nn.TransformerEncoderLayer(h, 4, 2 * h, batch_first=True,
                                         dropout=0.1, activation='gelu')
        self.tr = nn.TransformerEncoder(enc, layers,
                                        enable_nested_tensor=False)
        self.out = nn.Linear(h, n)

    def forward(self, x):
        z = self.proj(x) + self.pos[:, :x.shape[1]]
        mask = torch.triu(torch.ones(x.shape[1], x.shape[1],
                                     dtype=torch.bool), 1)
        z = self.tr(z, mask=mask)
        return self.out(z)


def main():
    eps = load()
    if len(eps) < 2:
        print(json.dumps({'error': 'episodes<%d' % 2}))
        return 1
    rng = np.random.RandomState(0)
    idx = np.arange(len(eps))
    rng.shuffle(idx)
    val = set(idx[-max(1, len(eps) // 5):].tolist())
    tr = [eps[i] for i in range(len(eps)) if i not in val]
    va = [eps[i] for i in range(len(eps)) if i in val]
    D = eps[0][0].shape[1]
    n = int(max(int(a.max()) for _, a in eps)) + 1
    Xtr = np.concatenate([s for s, _ in tr])
    Ytr = np.concatenate([a for _, a in tr])
    Xva = np.concatenate([s for s, _ in va])
    Yva = np.concatenate([a for _, a in va])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xtr = (Xtr - mu) / sd
    Xva = (Xva - mu) / sd
    T = 16
    xs, ys = [], []
    for i in range(T, len(Xtr)):
        xs.append(Xtr[i - T:i])
        ys.append(Ytr[i])
    xv, yv = [], []
    for i in range(T, len(Xva)):
        xv.append(Xva[i - T:i])
        yv.append(Yva[i])
    if len(xs) < 50:
        print(json.dumps({'error': 'windows<%d' % 50}))
        return 1
    m = TT(D, n)
    opt = torch.optim.Adam(m.parameters(), 1e-3)
    xt = torch.tensor(np.stack(xs)[:2000])
    yt = torch.tensor(np.array(ys)[:2000])
    for ep in range(15):
        opt.zero_grad()
        loss = nn.functional.cross_entropy(m(xt)[:, -1],
                                           yt.reshape(-1))
        loss.backward()
        opt.step()
        if ep % 5 == 0:
            print('epoch', ep, 'loss', round(float(loss), 3))
    with torch.no_grad():
        pv = m(torch.tensor(np.stack(xv)))[:, -1].argmax(1).numpy()
    res = {'episodes': len(eps), 'T': T, 'train_windows': len(xs),
           'val_windows': len(xv), 'top1': round(float((pv == np.array(yv)).mean()), 3),
           'note': '协议 demo；episodes 少，待 retention 后正式跑'}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
