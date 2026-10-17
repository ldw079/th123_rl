# -*- coding: utf-8 -*-
"""【消融基线】MLP 宏分类器训练 CLI（**非**本项目主架构）。

本项目主架构是"以自建小 LLM 为根基"的 `soku_arch/lm/`（token 序列 + 因果语言建模）。
本文件保留同类项目的范式（残差 MLP 直接吃连续特征）作为**消融对照**。
结论见 docs/RESULTS.md §3：同批行同切分下两者 top1 差异在噪声内（0.1811 vs 0.1817），
LLM 的优势体现在 top-5 排序（0.6164 vs 0.5609）与校准（ECE 0.0372 vs 0.0731）。

四方完整对照请用：python run.py compare --data <npz> --char reimu
"""

用法（在 D:\\temp\\soku_arch 下）：
  D:\\temp\\pyenv\\python.exe -m soku_arch.train --data D:\\temp\\th123_models\\distill_data_reimu.npz \
      --char reimu --split block --epochs 40 --out artifacts

产出：
  artifacts/<char>/<split>/model.pt        权重（含 ModelConfig）
  artifacts/<char>/<split>/spec.json       特征列 + 标准化统计（部署必须同源）
  artifacts/<char>/<split>/report.json     完整报告（指标 + 基线 + 混淆 + 训练曲线）
  artifacts/<char>/<split>/val_logits.npy  验证集 logits（供 ONNX 一致性/校准复核）
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn

from . import baselines, metrics
from .constants import LATENCY_BUDGET_MS
from .dataset import prepare
from .losses import MacroLoss, make_class_weights
from .model import ModelConfig, build_model


def top_confusions(logits: np.ndarray, y: np.ndarray, n_classes: int, k: int = 8) -> list:
    cm = metrics.confusion(logits, y, n_classes).copy()
    np.fill_diagonal(cm, 0)
    flat = np.dstack(np.unravel_index(np.argsort(-cm, axis=None), cm.shape))[0][:k]
    return [{"true": int(t), "pred": int(p), "count": int(cm[t, p])} for t, p in flat if cm[t, p] > 0]


def evaluate(model: nn.Module, X: torch.Tensor, y: torch.Tensor, batch: int = 8192) -> np.ndarray:
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, len(X), batch):
            out = model(X[i:i + batch])
            outs.append(out["logits"].numpy())
    return np.concatenate(outs, axis=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="soku_arch 训练")
    ap.add_argument("--data", required=True)
    ap.add_argument("--char", default=None)
    ap.add_argument("--split", default="block", choices=["block", "random", "group"])
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--model", default="mlp", choices=["mlp", "seq"])
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--hidden", type=int, default=192)
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--power", type=float, default=0.5, help="类平衡权重指数")
    ap.add_argument("--label-smoothing", type=float, default=0.05)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=0, help="0=自动")
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--no-baselines", action="store_true")
    args = ap.parse_args(argv)

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    if args.threads > 0:
        torch.set_num_threads(args.threads)

    if args.model == "seq":
        from .dataset import MISSING_GROUP_KEY_MSG
        raise SystemExit(
            "时序模型当前不可训练：数据无 match_id/tick_index，无法形成合法序列。\n"
            + MISSING_GROUP_KEY_MSG
        )

    t0 = time.perf_counter()
    prep = prepare(args.data, mode=args.split, val_frac=args.val_frac, seed=args.seed, char=args.char)
    spec = prep["spec"]
    n_macros = prep["n_macros"]
    Xtr, ytr = prep["train"].to_torch()
    Xva, yva = prep["val"].to_torch()

    cfg = ModelConfig(
        n_features=spec.dim, n_macros=n_macros, hidden=args.hidden,
        n_blocks=args.blocks, dropout=args.dropout,
    )
    model = build_model(args.model, cfg)

    counts = np.bincount(ytr.numpy(), minlength=n_macros)
    cw = make_class_weights(counts, power=args.power)
    crit = MacroLoss(class_weights=cw, label_smoothing=args.label_smoothing)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, args.epochs))

    print(f"[数据] {prep['char']} 有效 {prep['n_train'] + prep['n_val']} 行 "
          f"| 训练 {prep['n_train']} / 验证 {prep['n_val']} | 切分={args.split}")
    print(f"[体检] 死列={prep['health']['dead_columns']} 类别覆盖="
          f"{prep['health']['n_classes_used']}/{n_macros} 缺失宏={len(prep['health']['missing_macros'])} "
          f"不均衡比={prep['health']['imbalance_ratio']:.0f}:1")
    print(f"[特征] 输入维={spec.dim} 保留列={list(spec.names())} 丢弃列={list(spec.dropped)}")
    print(f"[模型] {args.model} 参数量={model.n_params():,} 类权重[min={cw.min():.3f} max={cw.max():.3f}]")

    g = torch.Generator().manual_seed(args.seed)
    best = {"macro_f1": -1.0, "epoch": -1, "state": None}
    history = []

    for ep in range(1, args.epochs + 1):
        model.train()
        perm = torch.randperm(len(Xtr), generator=g)
        tot, nb = 0.0, 0
        t_ep = time.perf_counter()
        for i in range(0, len(Xtr), args.batch):
            idx = perm[i:i + args.batch]
            out = model(Xtr[idx])
            losses = crit(out, {"y": ytr[idx]})
            opt.zero_grad(set_to_none=True)
            losses["total"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tot += float(losses["total"]); nb += 1
        sched.step()

        vl = evaluate(model, Xva, yva)
        m = metrics.summarize(vl, yva.numpy(), n_macros)
        history.append({"epoch": ep, "train_loss": tot / max(nb, 1), "val_loss": float(
            torch.nn.functional.cross_entropy(torch.from_numpy(vl), yva).item()),
            "val_top1": m["top1"], "val_macro_f1": m["macro_f1"], "lr": opt.param_groups[0]["lr"],
            "sec": time.perf_counter() - t_ep})
        if m["macro_f1"] > best["macro_f1"]:
            best = {"macro_f1": m["macro_f1"], "epoch": ep,
                    "state": {k: v.detach().clone() for k, v in model.state_dict().items()}}
        if ep % 5 == 0 or ep == 1:
            print(f"  epoch {ep:3d} loss={history[-1]['train_loss']:.4f} "
                  f"val_top1={m['top1']:.4f} val_macroF1={m['macro_f1']:.4f} "
                  f"({history[-1]['sec']:.1f}s)")

    if best["state"] is not None:
        model.load_state_dict(best["state"])
    vl = evaluate(model, Xva, yva)
    yv = yva.numpy()
    final = metrics.summarize(vl, yv, n_macros)

    report = {
        "char": prep["char"], "split": args.split, "model": args.model,
        "n_params": model.n_params(),
        "best_epoch": best["epoch"],
        "cfg": cfg.__dict__,
        "spec": spec.to_json(),
        "health": prep["health"],
        "class_weight": {"min": float(cw.min()), "max": float(cw.max()), "power": args.power},
        "final": final,
        "history": history,
        "top_confusions": top_confusions(vl, yv, n_macros),
        "train_seconds": time.perf_counter() - t0,
        "latency_budget_ms": LATENCY_BUDGET_MS,
    }

    if not args.no_baselines:
        Xv_np = prep["val"].x
        Xt_np = prep["train"].x
        maj = baselines.majority_logits(ytr.numpy(), len(yv), n_macros)
        report["baseline_majority"] = metrics.summarize(maj, yv, n_macros)
        lr_logits = baselines.logreg_logits(Xt_np, ytr.numpy(), Xv_np, n_macros)
        report["baseline_logreg"] = metrics.summarize(lr_logits, yv, n_macros)
        print(f"[基线] 多数类 top1={report['baseline_majority']['top1']:.4f} "
              f"| 逻辑回归 top1={report['baseline_logreg']['top1']:.4f}")
        report["js_vs_teacher"] = {
            "model": metrics.js_divergence(
                np.bincount(vl.argmax(1), minlength=n_macros),
                np.bincount(yv, minlength=n_macros)),
            "logreg": metrics.js_divergence(
                np.bincount(lr_logits.argmax(1), minlength=n_macros),
                np.bincount(yv, minlength=n_macros)),
        }

    outdir = os.path.join(args.out, prep["char"], args.split)
    os.makedirs(outdir, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "cfg": cfg.__dict__,
                "char": prep["char"], "n_macros": n_macros},
               os.path.join(outdir, "model.pt"))
    with open(os.path.join(outdir, "spec.json"), "w", encoding="utf-8") as f:
        json.dump(spec.to_json(), f, indent=2, ensure_ascii=False)
    with open(os.path.join(outdir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    np.save(os.path.join(outdir, "val_logits.npy"), vl)

    print(f"[结果] top1={final['top1']:.4f} top5={final['top5']:.4f} "
          f"macroF1={final['macro_f1']:.4f} ECE={final['ece_15bin']:.4f} "
          f"预测覆盖={final['pred_coverage']['n_predicted_classes']}/{n_macros}")
    print(f"[产物] {outdir}  (耗时 {report['train_seconds']:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
