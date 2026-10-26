# -*- coding: utf-8 -*-
"""H1 延迟基准 v2: KV cache 增量解码 + 动态量化 + batch.

CPU only（本机 torch 无 CUDA）。输出 JSON。
"""
import json
import statistics
import time

import torch
import torch.nn as nn


class CachedLayer(nn.Module):
    def __init__(self, d=128, heads=4):
        super().__init__()
        self.h = heads
        self.q = nn.Linear(d, d)
        self.k = nn.Linear(d, d)
        self.v = nn.Linear(d, d)
        self.o = nn.Linear(d, d)
        self.ff = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(),
                                nn.Linear(4 * d, d))
        self.ln1 = nn.LayerNorm(d)
        self.ln2 = nn.LayerNorm(d)

    def forward(self, x, kv=None):
        B, T, D = x.shape
        q = self.q(x).view(B, T, self.h, D // self.h).transpose(1, 2)
        k = self.k(x).view(B, T, self.h, D // self.h).transpose(1, 2)
        v = self.v(x).view(B, T, self.h, D // self.h).transpose(1, 2)
        if kv is not None:
            k = torch.cat([kv[0], k], dim=2)
            v = torch.cat([kv[1], v], dim=2)
        att = torch.softmax(q @ k.transpose(-2, -1) / (D // self.h) ** 0.5,
                            dim=-1)
        out = (att @ v).transpose(1, 2).reshape(B, T, D)
        x = self.ln1(x + self.o(out))
        x = self.ln2(x + self.ff(x))
        return x, (k, v)


class CachedModel(nn.Module):
    def __init__(self, d=128, layers=4, vocab=128):
        super().__init__()
        self.emb = nn.Embedding(vocab, d)
        self.layers = nn.ModuleList([CachedLayer(d) for _ in range(layers)])
        self.out = nn.Linear(d, vocab + 1)

    def prefill(self, x):
        x = self.emb(x)
        kv = [None] * len(self.layers)
        for i, l in enumerate(self.layers):
            x, kv[i] = l(x, kv[i])
        return x[:, -1], kv

    def step(self, tok, kv):
        x = self.emb(tok)
        for i, l in enumerate(self.layers):
            x, kv[i] = l(x, kv[i])
        return self.out(x[:, -1]), kv


def bench(T, n=1000, quant=False, d=128, layers=4, threads=2):
    torch.manual_seed(0)
    torch.set_num_threads(threads)
    m = CachedModel(d=d, layers=layers).eval()
    if quant:
        m = torch.quantization.quantize_dynamic(m, {nn.Linear}, dtype=torch.qint8)
    toks = torch.randint(0, 128, (1, T))
    with torch.inference_mode():
        _, kv = m.prefill(toks)
        for _ in range(20):
            _, kv = m.step(torch.randint(0, 128, (1, 1)), kv)
        ts = []
        for _ in range(n):
            t0 = time.perf_counter()
            _, kv = m.step(torch.randint(0, 128, (1, 1)), kv)
            ts.append((time.perf_counter() - t0) * 1000)
            if len(kv[0][0]) > T + 64:
                _, kv = m.prefill(toks)
    ts.sort()
    return {'T': T, 'quant': quant,
            'p50_ms': round(statistics.median(ts), 3),
            'p95_ms': round(ts[int(n * 0.95) - 1], 3),
            'p99_ms': round(ts[int(n * 0.99) - 1], 3)}


def main():
    torch.set_num_threads(2)
    out = {'cuda': torch.cuda.is_available(), 'results': []}
    for T in (16, 32):
        out['results'].append(bench(T, quant=False))
        out['results'].append(bench(T, quant=True))
    # 收窄变体: d64/2层/T8-16, 2 threads
    for T in (8, 16):
        out['results'].append(bench(T, quant=True, d=64, layers=2,
                                    threads=2))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    json.dump(out, open(r'D:\temp\scratch\h1_seq_bench_v2.json', 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
