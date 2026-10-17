# -*- coding: utf-8 -*-
"""神谕流 ↔ `.rep` 输入流的**分段对齐**，产出可直接训练的帧级样本。

为什么需要它（实测结论，见 `docs/REPLAY_PIPELINE.md §4.23`）：
  神谕流（游戏自播 `.rep` 时被动推回的状态）与 `.rep` 里的输入流**不是 1:1**：
  实测同一局 神谕 10,632 帧 vs rep 输入 10,349 条（差 283），
  且用"方向位↔位移"耦合定出的位移 `δ = 神谕帧 − rep 下标` 在回合结束后**跳变**
  （第 1 段 左46/右62 → 第 2 段 左127/右148，跳 ~82）。
  → `.rep` 少记了部分回合间演出帧。**按下标朴素配对会让标签整体错位**。

做法（每一步都可失败、可审计）：
  1. 用神谕 `score` 增量切段（每段 = 一个回合的战斗段）；
  2. **每段单独估计 δ**：最大化"方向位 h[k] 与 Δx[j]（j=k+δ）的分离度"，
     两侧位移之和作为目标函数（两侧应一致，取和比取绝对值更抗伪峰）；
     **δ 的约定（写死，避免 ±1 漂移）**：`Δx[j] = x[j+1]-x[j]` 与 `h[j-δ]` 配对，
     即"rep 第 k 条输入驱动**离开**神谕帧 k+δ 的那一步"，因此
     **神谕帧 j 的标签 = rep[j-δ]**。（这正是 STATUS 里那个 1 帧歧义：
     本模块固定用"动作先于下一步状态"的约定，不做隐式 ±1 补偿。）
  3. 映射：神谕帧 j → rep 下标 `j-δ`；越界或落在被丢弃窗口的帧记 `-1`（`bc_data` 会忽略）；
  4. **丢弃**：段首无对应输入的帧、每段开头 `δ_next-δ_cur` 帧（= rep 少记的演出帧）、
     最后一个回合结束之后的整段（比赛已终）；
  5. 审计：每段 δ、分离度、保留/丢弃帧数，全部写进 meta；分离度过低的段整段丢弃
     （宁可少，不要错配）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .input_codec import BattleInput

MIN_SEPARATION = 3.0        # 段级判据：分离度（px/帧）低于此判为"对齐不可信"
SEARCH_LO = -200
SEARCH_HI = 600
MIN_SEGMENT_FRAMES = 60


def round_bounds(score_l: np.ndarray, score_r: np.ndarray) -> list[int]:
    """总分增加的帧号（= 回合结束帧）。"""
    tot = np.asarray(score_l, dtype=np.float64) + np.asarray(score_r, dtype=np.float64)
    return [int(i) for i in range(1, len(tot)) if tot[i] > tot[i - 1]]


def direction_bits(raw: np.ndarray) -> np.ndarray:
    """原始 u16 BattleKeys 序列 → 方向位 H（-1/0/+1）；负值（占位）记 0。"""
    out = np.zeros(len(raw), dtype=np.float64)
    for i, v in enumerate(np.asarray(raw).reshape(-1)):
        iv = int(v)
        if iv >= 0:
            out[i] = BattleInput(iv).hv[0]
    return out


def _separation(dx: np.ndarray, h: np.ndarray, delta: int, lo: int, hi: int) -> tuple[float, int]:
    """在神谕帧区间 [lo,hi) 上，Δx[j] 与 h[j-delta] 的分离度（px/帧）与参与帧数。"""
    js = np.arange(max(lo, 0), min(hi, len(dx)))
    if js.size == 0:
        return float("nan"), 0
    ks = js - delta
    ok = (ks >= 0) & (ks < len(h)) & (h[np.clip(ks, 0, len(h) - 1)] != 0)
    js, ks = js[ok], ks[ok]
    if js.size < MIN_SEGMENT_FRAMES:
        return float("nan"), int(js.size)
    hh = h[ks]
    dd = dx[js]
    pos, neg = hh > 0, hh < 0
    if pos.sum() < 10 or neg.sum() < 10:
        return float("nan"), int(js.size)
    return float(dd[pos].mean() - dd[neg].mean()), int(js.size)


def estimate_shift(oracle_x: dict[int, np.ndarray], h: dict[int, np.ndarray],
                   lo: int, hi: int, *, search: tuple[int, int] = (SEARCH_LO, SEARCH_HI),
                   ) -> dict:
    """在区间 [lo,hi) 上联合两侧估计 δ（目标 = 两侧分离度之和）。"""
    dx = {s: np.diff(oracle_x[s]) for s in oracle_x}
    best = {"delta": None, "objective": -np.inf, "per_side": {}}
    for d in range(search[0], search[1] + 1):
        seps, ns, obj = {}, {}, 0.0
        valid = True
        for s in oracle_x:
            sep, n = _separation(dx[s], h[s], d, lo, hi)
            seps[s], ns[s] = sep, n
            if not np.isfinite(sep):
                valid = False
                break
            obj += sep
        if valid and obj > best["objective"]:
            best = {"delta": int(d), "objective": float(obj),
                    "per_side": {s: float(seps[s]) for s in seps},
                    "frames_used": {s: int(ns[s]) for s in ns}}
    return best


@dataclass
class AlignResult:
    """对齐结果：`inp[j]` 是神谕第 j 帧对应要喂的原始输入（-1 = 丢弃）。"""

    inp: np.ndarray                 # (N, 2) int32
    kept: np.ndarray                # (N,) bool
    audit: dict = field(default_factory=dict)


def build_aligned(oracle_x: dict[int, np.ndarray], score_l: np.ndarray, score_r: np.ndarray,
                  raw_inputs: np.ndarray, *, sides: tuple[int, ...] = (0, 1),
                  max_delta_jump: int = 1200) -> AlignResult:
    """神谕状态流 + rep 原始输入 → 对齐后的 `inp`（与驱动分片同义：每帧该侧要发的输入）。

    `oracle_x[s]` 为该侧横坐标序列（用于估计位移）；`raw_inputs` 形状 (M,2)，原始 u16。
    """
    n = len(score_l)
    raw = np.asarray(raw_inputs, dtype=np.int64)
    h = {s: direction_bits(raw[:, s]) for s in sides}
    ox = {s: np.asarray(oracle_x[s], dtype=np.float64) for s in sides}
    bounds = round_bounds(score_l, score_r)
    segs = list(zip([0] + bounds, bounds + [n]))
    # 末段是"最后一回合结束之后"（比赛已终）→ 整体丢弃
    play_segs = segs[:-1] if bounds else segs

    out = np.full((n, raw.shape[1]), -1, dtype=np.int32)
    kept = np.zeros(n, dtype=bool)
    audit_segs: list[dict] = []
    prev_delta: int | None = None

    for idx, (a, b) in enumerate(play_segs):
        if b - a < MIN_SEGMENT_FRAMES:
            audit_segs.append({"seg": idx, "lo": a, "hi": b, "frames": b - a,
                               "skipped": "segment_too_short"})
            continue
        # 段首的"rep 少记演出帧"要跳过：δ 相对上一段跳了多少就丢多少
        est = estimate_shift(ox, h, a, b)
        if est["delta"] is None:
            audit_segs.append({"seg": idx, "lo": a, "hi": b, "frames": b - a,
                               "skipped": "no_valid_shift"})
            continue
        delta = int(est["delta"])
        weak = (min(est["per_side"].values()) < MIN_SEPARATION) if est["per_side"] else True
        if weak:
            audit_segs.append({"seg": idx, "lo": a, "hi": b, "frames": b - a,
                               "delta": delta, "per_side": est["per_side"],
                               "skipped": "weak_alignment"})
            continue
        # 本段可用的神谕帧：跳过段首那些"上一回合演出"（δ 增量）
        head = a
        if prev_delta is not None:
            head = min(b, a + max(0, delta - prev_delta))
        js = np.arange(head, b)
        ks = js - delta
        ok = (ks >= 0) & (ks < len(raw))
        for s in sides:
            out[js[ok], s] = raw[ks[ok], s]
        kept[js[ok]] = True
        audit_segs.append({
            "seg": idx, "lo": a, "hi": b, "frames": b - a,
            "delta": delta, "per_side_separation": est["per_side"],
            "objective": est["objective"], "frames_used": est["frames_used"],
            "dropped_head": int(head - a), "dropped_tail": int(b - head - int(ok.sum())),
            "kept": int(ok.sum()), "skipped": None})
        prev_delta = delta

    if bounds:
        after = bounds[-1]
        audit_segs.append({"seg": len(play_segs), "lo": after, "hi": n,
                           "frames": n - after, "skipped": "after_match_end"})

    separations = [s.get("per_side_separation") for s in audit_segs
                   if s.get("per_side_separation")]
    min_sep = float(min(min(v.values()) for v in separations)) if separations else None
    played = [s for s in audit_segs if s.get("seg", 99) < len(play_segs)]
    reliable = bool(played) and all(s.get("skipped") is None for s in played)
    return AlignResult(inp=out, kept=kept, audit={
        "n_frames": int(n), "n_rep_inputs": int(len(raw)),
        "round_bounds": bounds, "n_segments": len(play_segs),
        "segments": audit_segs,
        "min_separation": min_sep,
        "kept_frames": int(kept.sum()),
        "kept_ratio": float(kept.mean()) if n else 0.0,
        "reliable": reliable,
        "note": "δ = 神谕帧 − rep 下标；每段单独估计；段首按 δ 增量丢弃（rep 少记的演出帧）；"
                "最后一回合结束之后整段丢弃。",
    })


__all__ = ["round_bounds", "direction_bits", "estimate_shift", "build_aligned",
           "AlignResult", "MIN_SEPARATION", "SEARCH_LO", "SEARCH_HI"]
