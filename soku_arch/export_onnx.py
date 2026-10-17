# -*- coding: utf-8 -*-
"""导出 SokuLM 到 ONNX，并用 onnxruntime 做**数值一致性交叉验证** + INT8 动态量化。

部署形态的选择（有依据）：
  决策路径只需要"给定完整局面序列 -> 宏 logits"，即一次全序列前向（prefill）。
  因此**不导出 KV-cache 增量图**：它会把图复杂化（多输入输出、动态拼接），
  而收益为零 —— 每次决策本来就是一次独立前缀。单步宏决策不需要自回归多 token。

流程：
  1. torch.onnx.export（固定 batch=1、固定 T，opset 17）
  2. ORT 加载 -> 与 torch 输出逐元素比对（max|Δ| 与 top1 一致性）
  3. 延迟 P50/P95/P99（多线程配置）
  4. INT8 动态量化 -> 再次一致性 + 延迟（诚实报告是否真的有收益）

用法：
  python run.py export --ckpt artifacts\\reimu\\lm\\block\\ckpt.pt
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn

from .lm.sample import load_ckpt


class LMForExport(nn.Module):
    """只输出 logits 的导出包装（去掉 KV cache 返回值）。"""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        logits, _ = self.model(input_ids, caches=None)
        return logits


def pcts(xs: list[float]) -> dict:
    a = np.asarray(xs, dtype=np.float64)
    return {"p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)),
            "p99": float(np.percentile(a, 99)), "mean": float(a.mean()), "n": int(a.size)}


def ort_latency(path: str, feeds: np.ndarray, iters: int = 50, warmup: int = 10,
                threads: int | None = None) -> tuple[dict, np.ndarray]:
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if threads is not None:
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
    sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    out = None
    ts = []
    for i in range(iters + warmup):
        t0 = time.perf_counter()
        out = sess.run(None, {name: feeds})[0]
        if i >= warmup:
            ts.append((time.perf_counter() - t0) * 1e3)
    return pcts(ts), out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SokuLM ONNX 导出 + 一致性验证")
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--corpus", default=None, help="缺省取 ckpt 同目录 corpus.npz")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--threads", nargs="*", type=int, default=[1, 4, 0])
    ap.add_argument("--quantize", action="store_true", default=True)
    ap.add_argument("--no-quantize", dest="quantize", action="store_false")
    args = ap.parse_args(argv)

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.ckpt))
    corpus_path = args.corpus or os.path.join(outdir, "corpus.npz")
    model, tok, ck = load_ckpt(args.ckpt)
    T = int(ck["seq_len"])
    wrapper = LMForExport(model).eval()

    # 取一条真实局面作为导出输入
    z = np.load(corpus_path)
    ids = z["ids"]
    sample = ids[:1].astype(np.int64)
    if sample.shape[1] != T:
        T = sample.shape[1]

    onnx_path = os.path.join(outdir, "sokulm.onnx")
    with torch.no_grad():
        ref = wrapper(torch.from_numpy(sample)).numpy()
    torch.onnx.export(
        wrapper, (torch.from_numpy(sample),), onnx_path,
        input_names=["input_ids"], output_names=["logits"],
        opset_version=17, do_constant_folding=True, dynamo=False,
    )
    print(f"[导出] {onnx_path}  ({os.path.getsize(onnx_path)/1e6:.2f} MB)  T={T} "
          f"vocab={ck['lm_cfg']['vocab_size']}")

    report = {"ckpt": args.ckpt, "onnx": onnx_path, "seq_len": T,
              "n_params": model.n_params(), "variants": {}}

    variants = [("fp32", onnx_path, 1.0)]
    if args.quantize:
        try:
            from onnxruntime.quantization import QuantType, quantize_dynamic

            qpath = os.path.join(outdir, "sokulm_int8.onnx")
            quantize_dynamic(onnx_path, qpath, weight_type=QuantType.QInt8)
            variants.append(("int8_dynamic", qpath, os.path.getsize(qpath) / os.path.getsize(onnx_path)))
        except Exception as exc:  # noqa: BLE001
            print(f"[警告] INT8 量化失败: {type(exc).__name__}: {exc}")

    for name, path, size_ratio in variants:
        lat, out = ort_latency(path, sample, iters=args.iters, threads=1)
        diff = float(np.max(np.abs(out - ref)))
        agree = float((out.argmax(-1) == ref.argmax(-1)).mean())
        row = {"file": path, "size_mb": os.path.getsize(path) / 1e6,
               "size_ratio_vs_fp32": size_ratio, "latency_ms_threads1": lat,
               "max_abs_diff_vs_torch": diff, "top1_agree_with_torch": agree, "by_threads": {}}
        print(f"[{name}] 大小 {row['size_mb']:.2f}MB  1线程 P50={lat['p50']:.2f} "
              f"P95={lat['p95']:.2f} P99={lat['p99']:.2f} ms  "
              f"max|Δ|={diff:.2e} top1一致={agree:.4f}")
        for th in args.threads:
            if th == 1:
                continue
            lat_th, _ = ort_latency(path, sample, iters=args.iters, threads=(th or None))
            row["by_threads"][str(th)] = lat_th
            print(f"      threads={th or 'default'}: P50={lat_th['p50']:.2f} "
                  f"P95={lat_th['p95']:.2f} P99={lat_th['p99']:.2f} ms")
        report["variants"][name] = row

    with open(os.path.join(outdir, "onnx_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[产物] {os.path.join(outdir, 'onnx_report.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
