# -*- coding: utf-8 -*-
"""成熟预训练小模型的接入层（HF transformers）+ 实测延迟探针。

设计原则：**先用延迟裁掉不合格模型，再谈精度。** 
帧级决策密度下，模型能不能上线是硬门槛（用户约束），因此这里只做两件事：
  1. 把局面序列化成 prompt（含 few-shot 示例，示例数直接决定 prefill 长度）
  2. 实测 prefill 与逐 token 解码的 P50/P95/P99，判定是否适配预算
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .constants import FEATURE_NAMES, WEATHER_NAMES

# 动作的自然语言化（verbalizer）。真实部署应把宏库名称表注入；
# 这里用 <mK> 符号 + few-shot 建立映射，避免把外部文件硬编码进本项目。
MACRO_SYMBOL = "m{}"


@dataclass
class PromptSpec:
    n_shots: int = 2
    n_features: int = 11
    n_macros: int = 55
    goal: str | None = None


SYSTEM_PROMPT = (
    "You are the decision layer of a Touhou Hisoutensoku bot. "
    "Read the battle state and output exactly one macro action id.\n"
    "State fields (in order): " + ", ".join(FEATURE_NAMES) + ".\n"
    "Action ids: " + MACRO_SYMBOL.format("0") + ".." + MACRO_SYMBOL.format("{n-1}") + ".\n"
    "Answer with the single token ACTION=<mK> and nothing else."
)


def _fmt_state(feats: np.ndarray) -> str:
    parts = []
    for i, name in enumerate(FEATURE_NAMES[: len(feats)]):
        v = float(feats[i])
        parts.append(f"{name}={v:.2f}" if not float(v).is_integer() else f"{name}={int(v)}")
    return " ".join(parts)


def build_prompt(spec: PromptSpec, tokenizer, sample_feats: np.ndarray | None = None) -> dict:
    """构造真实长度的 prompt，并返回 token 数（延迟的主因）。"""
    rng = np.random.default_rng(0)
    lines = [SYSTEM_PROMPT.format(n=spec.n_macros), ""]
    if spec.goal:
        lines.append(f"Goal: {spec.goal}")
    for _ in range(spec.n_shots):
        f = rng.normal(loc=400, scale=300, size=spec.n_features)
        f[2] = float(rng.random() < 0.25)
        f[6:8] = (rng.random(2) < 0.5).astype(float)
        f[8] = float(rng.random() < 0.5)
        f[10] = float(rng.random() < 0.35)
        k = int(rng.integers(0, spec.n_macros))
        lines.append(f"STATE {_fmt_state(f)} -> ACTION={MACRO_SYMBOL.format(k)}")
    if sample_feats is None:
        sample_feats = rng.normal(loc=400, scale=300, size=spec.n_features)
        sample_feats[2] = 0.0
    lines.append(f"STATE {_fmt_state(np.asarray(sample_feats))} -> ACTION=")
    text = "\n".join(lines)
    ids = tokenizer(text, return_tensors="pt")["input_ids"]
    return {"text": text, "n_tokens": int(ids.shape[1]), "input_ids": ids}


class MatureLM:
    """极薄的 HF 包装：只暴露本基准需要的接口。"""

    def __init__(self, model, tokenizer, name: str):
        self.model = model
        self.tokenizer = tokenizer
        self.name = name

    def n_params(self) -> int:
        return sum(p.numel() for p in self.model.parameters())

    def encode(self, text: str):
        return self.tokenizer(text, return_tensors="pt")["input_ids"]


def load_mature_model(name: str, dtype: str = "float32") -> tuple[MatureLM, object]:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise SystemExit(
            "缺少 transformers/torch。请安装到项目内部：\n"
            "  pip install --target D:\\temp\\soku_arch\\.pylibs transformers huggingface_hub "
            "tokenizers safetensors regex pyyaml requests tqdm packaging\n"
            "并在 run.py 的 sys.path 中加入该目录。\n"
            f"原始错误: {exc}"
        )
    td = {"float32": torch.float32, "bfloat16": torch.bfloat16}[dtype]
    tok = AutoTokenizer.from_pretrained(name)
    try:
        model = AutoModelForCausalLM.from_pretrained(name, dtype=td)
    except TypeError:  # 旧版 transformers 用 torch_dtype
        model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=td)
    model.eval()
    return MatureLM(model, tok, name), tok


def _pcts(xs: list[float]) -> dict:
    a = np.asarray(xs, dtype=np.float64)
    return {
        "p50": float(np.percentile(a, 50)),
        "p95": float(np.percentile(a, 95)),
        "p99": float(np.percentile(a, 99)),
        "mean": float(a.mean()), "min": float(a.min()), "max": float(a.max()),
        "n": int(a.size),
    }


def probe_latency(
    lm: MatureLM, tokenizer, text: str, iters: int = 30, warmup: int = 3,
    max_new_tokens: int = 8,
) -> dict:
    """实测：prefill（全 prompt 一次前向）与 decode（逐 token 增量）延迟。"""
    import torch

    input_ids = tokenizer(text, return_tensors="pt")["input_ids"]
    prefill, decode_total, total = [], [], []
    model = lm.model

    with torch.inference_mode():
        for it in range(iters + warmup):
            t0 = time.perf_counter()
            out = model(input_ids, use_cache=True)
            t1 = time.perf_counter()

            past = out.past_key_values
            nxt = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
            t2 = time.perf_counter()
            for _ in range(max_new_tokens):
                out = model(nxt, past_key_values=past, use_cache=True)
                past = out.past_key_values
                nxt = out.logits[:, -1, :].argmax(dim=-1, keepdim=True)
            t3 = time.perf_counter()

            if it >= warmup:
                prefill.append((t1 - t0) * 1e3)
                decode_total.append((t3 - t2) * 1e3)
                total.append((t3 - t0) * 1e3)

    dec_per_tok = [x / max(1, max_new_tokens) for x in decode_total]
    return {
        "prefill_ms": _pcts(prefill),
        "decode_per_token_ms": _pcts(dec_per_tok),
        "total_ms": _pcts(total),
        "max_new_tokens": max_new_tokens,
        "prompt_chars": len(text),
    }


__all__ = ["PromptSpec", "SYSTEM_PROMPT", "MACRO_SYMBOL", "MatureLM",
           "load_mature_model", "build_prompt", "probe_latency"]
