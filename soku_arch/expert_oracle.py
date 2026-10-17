# -*- coding: utf-8 -*-
"""接入兄弟项目的**专家（神谕）分片** —— `th123_rl/data/oracle/shards/*.npz`。

他们的分片格式（191 局、198.5 MB，2026-09-24 产出）：

| 键 | 形状 | 含义 |
|---|---|---|
| `x` | (N, 11) f8 | 兄弟项目的 11 列：hp_l, hp_r, **x_l×10**, **x_r×10**, act_l, act_r, score_l, score_r, weather_displayed, weather_active, weather_timer |
| `inputs` | (M, 2) u16 | `.rep` 原始输入条目对（**M ≠ N**：回合间演出帧没被 rep 记录） |
| `rounds` | (K, 3) i8 | [帧, score_x, score_y] |
| `meta` | JSON | rep 名/角色/卡组/种子/n_inputs/frames/score_final… |

**本模块做三件诚实的事**（不美化差异）：

1. **列名对齐**：映射到本项目 20 列口径；他们没存的字段（spirit/y/airBorne/pose/cardGauge/
   hand_n）一律写 `NaN`，由 `frame_obs` 按"不猜"原则填 0 并在 `AVAILABILITY` 里点名。
2. **左右修正**：**他们的 `inputs[:,0]` 是右、`[:,1]` 是左**（本项目 2026-09-24 用
   mod 输入日志逐帧精确匹配 1.0000 证明 `.rep` 交错是 `[右,左]`）。
   本模块输出统一口径 `[左,右]`，即 `inputs[:, [1,0]]`。
3. **不假装能直接做帧级标签**：`inputs` 与 `x` 的帧轴**不同长度**（演出帧缺失），
   按 `k` 朴素配对必然错位。所以本模块**不**产出可训练分片，只产出
   （一）语料清单/统计、（二）用于批量重采的 rep 名列表 —— 真正的帧级标签要靠
   `run.py observe-replay --input-log`（mod 同帧记录，构造性对齐）。
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np

# 兄弟项目 x 的 11 列
SIBLING_COLS: tuple[str, ...] = (
    "hp_l", "hp_r", "x_l10", "x_r10", "act_l", "act_r",
    "score_l", "score_r", "weather_displayed", "weather_active", "weather_timer")

# 本项目 20 列口径（每侧 10 列）
OUR_SIDE_COLS: tuple[str, ...] = ("hp", "spirit", "x", "y", "action", "pose",
                                  "airBorne", "cardGauge", "hand_n", "score")
# 他们有的列 → 本项目的列下标（每侧）
HAVE_SIDE = {"hp": 0, "x": 2, "action": 4}
# 他们没存、我们需要的列（写 NaN，由 frame_obs 按"不猜"填 0）
MISSING_SIDE = ("spirit", "y", "pose", "airBorne", "cardGauge", "hand_n")


def load_sibling_shard(path: str) -> dict:
    """读一个兄弟分片 → 本项目的规范化字典（缺失列 = NaN，`hand` = -1 占位）。"""
    z = np.load(path, allow_pickle=True)
    x11 = np.asarray(z["x"], dtype=np.float64)
    if x11.ndim != 2 or x11.shape[1] != 11:
        raise ValueError(f"{os.path.basename(path)}: x 形状 {x11.shape} 不是 (N,11)")
    n = len(x11)
    x = np.full((n, 2 * len(OUR_SIDE_COLS)), np.nan, dtype=np.float64)
    for side, base in ((0, 0), (1, 10)):
        src = {"hp": 0 if side == 0 else 1,
               "x": 2 if side == 0 else 3,
               "action": 4 if side == 0 else 5}
        for col, src_i in src.items():
            x[:, base + OUR_SIDE_COLS.index(col)] = x11[:, src_i]
            if col == "x":
                x[:, base + OUR_SIDE_COLS.index("x")] /= 10.0     # 他存的是 ×10 定点
        x[:, base + OUR_SIDE_COLS.index("score")] = x11[:, 6 if side == 0 else 7]
    raw = np.asarray(z["inputs"], dtype=np.int64)
    if raw.ndim != 2 or raw.shape[1] != 2:
        raise ValueError(f"{os.path.basename(path)}: inputs 形状 {raw.shape} 不是 (M,2)")
    # **左右修正**：他们 [0]=右、[1]=左 → 我们统一 [左, 右]
    inp = np.stack([raw[:, 1], raw[:, 0]], axis=1).astype(np.int32)
    meta = json.loads(str(z["meta"].item())) if "meta" in z.files else {}
    meta = dict(meta)
    meta.setdefault("frames", int(n))
    meta["source_shard"] = os.path.basename(path)
    meta["inp_side_order"] = "normalized_to_[left,right] (sibling stored [right,left])"
    meta["missing_side_cols"] = list(MISSING_SIDE)
    meta["n_inputs"] = int(len(inp))
    rounds = np.asarray(z["rounds"], dtype=np.int64) if "rounds" in z.files else np.zeros((0, 3), np.int64)
    return {"x": x, "inp": inp, "hand": np.full((n, 2, 5), -1, dtype=np.int16),
            "rounds": rounds, "meta": meta, "n11": n}


def scan_sibling_dir(root: str) -> list[str]:
    return sorted(glob.glob(os.path.join(root, "*.npz")))


def index_rep_corpus(roots: list[str]) -> dict[str, str]:
    """把本地 `.rep` 语料建成 {basename: fullpath}（用于按名找他们的 191 局）。"""
    out: dict[str, str] = {}
    for root in roots:
        for dp, _d, fs in os.walk(root):
            for fn in fs:
                if fn.lower().endswith(".rep"):
                    out.setdefault(fn, os.path.join(dp, fn))
    return out


def corpus_report(shard_dir: str, rep_roots: list[str]) -> dict:
    """统计他们的语料 + 本地能对上多少（决定能不能自己重采）。"""
    files = scan_sibling_dir(shard_dir)
    idx = index_rep_corpus(rep_roots)
    frames = inputs = 0
    per_char: dict[str, int] = {}
    scores: dict[str, int] = {}
    matched: list[str] = []
    missing: list[str] = []
    bad: list[str] = []
    for p in files:
        try:
            d = load_sibling_shard(p)
        except Exception as exc:                              # noqa: BLE001
            bad.append(f"{os.path.basename(p)}: {exc}")
            continue
        m = d["meta"]
        frames += d["n11"]
        inputs += len(d["inp"])
        key = f"{m.get('char_x')}v{m.get('char_y')}"
        per_char[key] = per_char.get(key, 0) + 1
        sc = m.get("score_final")
        if isinstance(sc, (list, tuple)) and len(sc) == 2:
            k = f"{sc[0]}:{sc[1]}"
            scores[k] = scores.get(k, 0) + 1
        rep = m.get("rep") or ""
        if rep in idx:
            matched.append(rep)
        else:
            missing.append(rep)
    return {"n_shards": len(files), "n_bad": len(bad), "bad": bad[:10],
            "total_frames": frames, "total_inputs": inputs,
            "per_matchup": dict(sorted(per_char.items(), key=lambda kv: -kv[1])),
            "score_final_dist": dict(sorted(scores.items(), key=lambda kv: -kv[1])),
            "n_rep_matched": len(matched), "n_rep_missing": len(missing),
            "matched_sample": matched[:3], "missing_sample": missing[:3],
            "rep_roots": rep_roots, "n_local_reps": len(idx)}


__all__ = ["SIBLING_COLS", "OUR_SIDE_COLS", "MISSING_SIDE", "load_sibling_shard",
           "scan_sibling_dir", "index_rep_corpus", "corpus_report"]
