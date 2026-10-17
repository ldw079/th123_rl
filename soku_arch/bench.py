# -*- coding: utf-8 -*-
"""延迟压测：SokuLM（torch 侧）与 MLP 基线对比，判定是否适配决策密度。

测三件事：
  1. prefill：整段局面序列一次前向（= 决策路径的真实成本）
  2. decode/token：KV-cache 增量解码单 token 成本（若要做"生成计划"才需要）
  3. 线程数扫描：CPU 部署必须显式定线程，否则 P99 抖动大

同时把 MLP 基线拉进来做**同口径对比**：回答"用 LLM 换来了什么、代价是多少"。
判据来自 tools/decision_budget.py 的实测预算：
  口径A 每帧决策   16.13 ms
  口径B 宏层决策   最短宏 96.8 ms

用法：
  python run.py bench --ckpt artifacts\\reimu\\lm\\block\\ckpt.pt [--mlp-ckpt ...]
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import torch

from .lm.sample import load_ckpt


def pcts(xs: list[float]) -> dict:
    a = np.asarray(xs, dtype=np.float64)
    return {"p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)),
            "p99": float(np.percentile(a, 99)), "mean": float(a.mean()),
            "min": float(a.min()), "max": float(a.max()), "n": int(a.size)}


def bench_forward(model, ids: torch.Tensor, iters: int, warmup: int,
                  measure_decode: bool = True) -> tuple[dict, dict]:
    """返回 (prefill 延迟, decode/单token 延迟)。measure_decode=False 时只测前向。"""
    pre, dec = [], []
    with torch.inference_mode():
        for i in range(iters + warmup):
            t0 = time.perf_counter()
            out, _ = model(ids)
            t1 = time.perf_counter()
            if i >= warmup:
                pre.append((t1 - t0) * 1e3)
        if measure_decode:
            # 增量解码：先 prefill 建 cache，再逐 token
            for i in range(iters + warmup):
                out, caches = model(ids)
                nxt = out[:, -1, :].argmax(-1, keepdim=True)
                t0 = time.perf_counter()
                model(nxt, caches=caches, pos_offset=ids.shape[1])
                t1 = time.perf_counter()
                if i >= warmup:
                    dec.append((t1 - t0) * 1e3)
    return pcts(pre), (pcts(dec) if dec else {})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="部署延迟压测")
    ap.add_argument("--ckpt", required=True, help="SokuLM ckpt.pt")
    ap.add_argument("--mlp-ckpt", default=None, help="可选：MLP 基线 ckpt 对比")
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--threads", nargs="*", type=int, default=[1, 2, 4, 0])
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    outdir = os.path.dirname(os.path.abspath(args.ckpt))
    corpus = os.path.join(outdir, "corpus.npz")
    model, tok, ck = load_ckpt(args.ckpt)
    ids_np = np.load(corpus)["ids"][:1].astype(np.int64)
    ids = torch.from_numpy(ids_np)
    budget_frame, budget_decision = 16.13, 96.8   # 来自 tools/decision_budget.py

    report = {"ckpt": args.ckpt, "n_params": model.n_params(), "seq_len": int(ids.shape[1]),
              "budget": {"per_frame_ms": budget_frame, "min_macro_decision_ms": budget_decision},
              "threads": {}}
    print(f"[模型] SokuLM 参数量={model.n_params():,} 序列长度={ids.shape[1]} "
          f"（预算: 每帧 {budget_frame}ms / 宏层 {budget_decision}ms）")
    for th in args.threads:
        if th > 0:
            torch.set_num_threads(th)
        pre, dec = bench_forward(model, ids, args.iters, args.warmup)
        row = {"prefill_ms": pre, "decode_per_token_ms": dec,
               "threads": torch.get_num_threads()}
        row["fits_per_frame"] = pre["p95"] <= budget_frame
        row["fits_macro_decision"] = pre["p95"] <= budget_decision
        report["threads"][str(th)] = row
        print(f"  threads={row['threads']:2d}: prefill P50={pre['p50']:7.2f} P95={pre['p95']:7.2f} "
              f"P99={pre['p99']:7.2f} ms | decode/token P50={dec['p50']:6.2f} P95={dec['p95']:6.2f} "
              f"| 每帧={'✓' if row['fits_per_frame'] else '✗'} 宏层={'✓' if row['fits_macro_decision'] else '✗'}")

    if args.mlp_ckpt:
        from .model import MacroPolicyNet, ModelConfig

        ck2 = torch.load(args.mlp_ckpt, map_location="cpu", weights_only=False)
        cfg = ModelConfig(**{k: v for k, v in ck2["cfg"].items()})
        mlp = MacroPolicyNet(cfg).eval()
        mlp.load_state_dict(ck2["state_dict"])
        x = torch.randn(1, cfg.n_features)
        pre, _ = bench_forward(lambda a, **k: (mlp(a), None), x, args.iters, args.warmup,
                               measure_decode=False)
        report["mlp_baseline"] = {"prefill_ms": pre, "n_params": mlp.n_params(),
                                  "fits_per_frame": pre["p95"] <= budget_frame}
        print(f"[MLP 基线] 参数量={mlp.n_params():,} 单次 P50={pre['p50']:.3f} "
              f"P95={pre['p95']:.3f} P99={pre['p99']:.3f} ms")
        ref = report["threads"].get("1") or next(iter(report["threads"].values()), None)
        if ref:
            print(f"[代价比] SokuLM/MLP 前向 P50 比值 ≈ "
                  f"{ref['prefill_ms']['p50']/max(pre['p50'], 1e-9):.1f}x")

    out = args.out or os.path.join(outdir, "bench.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[产物] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
