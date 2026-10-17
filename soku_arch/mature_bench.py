# -*- coding: utf-8 -*-
"""成熟小模型（预训练）在本机的**实测**延迟基准 —— 判断能否适配帧级决策密度。

不猜、不查论文：在本机 CPU 上用真实 prompt 实测 prefill 与逐 token 解码延迟，
给出 P50/P95/P99，并与两个预算口径比较：
  * 口径A 每帧决策 : 16.67 ms（60fps）
  * 口径B 宏层决策 : 由 tools/decision_budget.py 得出的"最短宏时长"

prompt 构造贴近真实部署：系统指令 + 局面序列化 + k 个 few-shot 示例 + 待决策局面。
few-shot 数量直接影响 prefill 长度，是延迟主因，所以 --shots 可扫。

用法：
  python run.py mature-bench --model HuggingFaceTB/SmolLM2-135M-Instruct --shots 0 2 4
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time

import numpy as np

from .constants import FEATURE_NAMES, MACRO_COUNT, WEATHER_NAMES
from .mature import (
    PromptSpec, build_prompt, load_mature_model, probe_latency,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="成熟小模型延迟基准")
    ap.add_argument("--model", default="HuggingFaceTB/SmolLM2-135M-Instruct")
    ap.add_argument("--shots", nargs="*", type=int, default=[0, 2, 4])
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--threads", nargs="*", type=int, default=[0])
    ap.add_argument("--max-new-tokens", type=int, default=8)
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16"])
    ap.add_argument("--out", default=os.path.join("artifacts", "mature_bench.json"))
    args = ap.parse_args(argv)

    import torch

    torch.set_grad_enabled(False)
    print(f"[加载] {args.model} dtype={args.dtype}")
    t0 = time.perf_counter()
    model, tok = load_mature_model(args.model, dtype=args.dtype)
    print(f"  加载耗时 {time.perf_counter()-t0:.1f}s  参数量={model.n_params():,}")

    results = []
    for shots in args.shots:
        spec = PromptSpec(n_shots=int(shots), n_features=len(FEATURE_NAMES), n_macros=MACRO_COUNT["reimu"])
        prompt = build_prompt(spec, tok)
        n_prompt_tokens = prompt["n_tokens"]
        for th in args.threads:
            if th > 0:
                torch.set_num_threads(th)
            r = probe_latency(
                model, tok, prompt["text"], iters=args.iters, warmup=args.warmup,
                max_new_tokens=args.max_new_tokens,
            )
            row = {
                "model": args.model, "shots": int(shots), "threads": torch.get_num_threads(),
                "dtype": args.dtype, "prompt_tokens": n_prompt_tokens,
                "prefill_ms": r["prefill_ms"], "decode_per_token_ms": r["decode_per_token_ms"],
                "total_ms": r["total_ms"], "n_params": model.n_params(),
            }
            row["fits_per_frame_16_67ms"] = row["total_ms"]["p95"] <= 16.667
            row["fits_decision_50ms"] = row["total_ms"]["p95"] <= 50.0
            row["fits_decision_100ms"] = row["total_ms"]["p95"] <= 100.0
            results.append(row)
            print(f"[shots={shots} threads={row['threads']} prompt_tok={n_prompt_tokens}] "
                  f"prefill P50={r['prefill_ms']['p50']:.1f} P95={r['prefill_ms']['p95']:.1f} | "
                  f"decode/token P50={r['decode_per_token_ms']['p50']:.2f} "
                  f"P95={r['decode_per_token_ms']['p95']:.2f} | "
                  f"total P50={row['total_ms']['p50']:.1f} P95={row['total_ms']['p95']:.1f} "
                  f"P99={row['total_ms']['p99']:.1f} ms")
            print(f"    适配: 每帧16.67ms={'是' if row['fits_per_frame_16_67ms'] else '否'}  "
                  f"宏层50ms={'是' if row['fits_decision_50ms'] else '否'}  "
                  f"宏层100ms={'是' if row['fits_decision_100ms'] else '否'}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=2, ensure_ascii=False)
    print(f"[产物] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
