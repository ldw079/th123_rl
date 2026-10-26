# -*- coding: utf-8 -*-
"""H1 延迟基准: T=16/32 因果 Transformer batch1 CPU/GPU.

离线只读；不接训练。产出 JSON: D:\\temp\\scratch\\h1_seq_bench_20261026.json
"""
import json
import os
import statistics
import time

import torch
import torch.nn as nn

OUT = r'D:\temp\scratch\h1_seq_bench_20261026.json'


class TinyCausal(nn.Module):
    def __init__(self, d=128, layers=4, heads=4, vocab=128):
        super().__init__()
        self.emb = nn.Embedding(vocab, d)
        self.pos = nn.Parameter(torch.zeros(1, 64, d))
        layer = nn.TransformerEncoderLayer(d, heads, 4 * d, batch_first=True,
                                           dropout=0.0, activation='gelu')
        self.tr = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.out = nn.Linear(d, vocab + 1)

    def forward(self, x):
        h = self.emb(x) + self.pos[:, :x.shape[1]]
        mask = torch.triu(torch.ones(x.shape[1], x.shape[1],
                                     dtype=torch.bool), 1)
        h = self.tr(h, mask=mask)
        return self.out(h[:, -1])


def bench(dev, T, n=100):
    torch.manual_seed(0)
    m = TinyCausal().to(dev).eval()
    x = torch.randint(0, 128, (1, T), device=dev)
    with torch.no_grad():
        for _ in range(10):
            m(x)
        if dev == 'cuda':
            torch.cuda.synchronize()
        ts = []
        for _ in range(n):
            t0 = time.perf_counter()
            m(x)
            if dev == 'cuda':
                torch.cuda.synchronize()
            ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return {'device': dev, 'T': T, 'params': sum(p.numel() for p in m.parameters()),
            'p50_ms': round(statistics.median(ts), 3),
            'p99_ms': round(ts[int(n * 0.99) - 1], 3)}


def main():
    torch.set_num_threads(2)
    res = []
    for T in (16, 32):
        res.append(bench('cpu', T))
        if torch.cuda.is_available():
            res.append(bench('cuda', T))
    out = {'results': res, 'ts': time.time(),
           'note': 'd128/4层/4头/vocab128，batch1，含 mask；H1 目标 5-10ms'}
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
