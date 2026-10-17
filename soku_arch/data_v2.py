# -*- coding: utf-8 -*-
"""X_v2 容器：全面观测数据集的**落盘格式、严格校验、旧数据迁移适配**。

为什么需要它：
  旧 distill 档只有 11 维 `X`，且第 3 列是标签载体（见 docs/DATA_CONTRACT.md）。
  观测 v2 要求 153 维标量 + 变长弹幕集合，另加 `match_id/tick/prev_macro/legal_mask/outcome`。
  在真机采集出 X_v2 之前，本模块提供：
    * 明确的容器格式（键名/形状/dtype/取值范围）与**严格校验**（不合规大声失败）
    * `from_legacy_11`：把旧数据**公平地**搬进 v2 管线（走 legacy_compat 兼容块，
      让新旧对照的唯一变量只剩读数路径，而不是"少 5 个特征"）
    * `coverage_report`：逐组统计"有多少维真的带信息"（零方差维 = 没数据），
      避免"看起来 164 维、实际只有 11 维在用"的自我欺骗
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from .constants import FEATURE_NAMES, MACRO_COUNT, N_FEATURES
from .observation import LEGACY_COMPAT_FIELDS, ObservationSpec

REQUIRED_KEYS: tuple[str, ...] = ("dense", "bullets", "bullet_mask", "y")
OPTIONAL_KEYS: tuple[str, ...] = ("match_id", "tick", "prev_macro", "legal_mask",
                                 "outcome", "mod_hash")
# 契约要求但仍常缺失的键（缺了就要在报告里点名，而不是静默通过）
CONTRACT_KEYS: tuple[str, ...] = ("match_id", "tick", "prev_macro", "legal_mask", "outcome")


@dataclass
class Xv2:
    dense: np.ndarray                 # (N, dense_dim) float32, 每列 ∈ [0,1]
    bullets: np.ndarray               # (N, K, D) float32
    bullet_mask: np.ndarray           # (N, K) float32 0/1
    y: np.ndarray                     # (N,) int64 宏 ID
    match_id: np.ndarray | None = None
    tick: np.ndarray | None = None
    prev_macro: np.ndarray | None = None
    legal_mask: np.ndarray | None = None   # (N, M) uint8
    outcome: np.ndarray | None = None
    mod_hash: str | None = None
    meta: dict = field(default_factory=dict)

    # ---------------- 校验 ----------------
    def validate(self, spec: ObservationSpec | None = None) -> dict:
        spec = spec or ObservationSpec(include_legacy_compat=self.dense.shape[1] != 153)
        errs: list[str] = []
        n = self.dense.shape[0]

        if self.dense.dtype != np.float32:
            errs.append(f"dense dtype 应为 float32，实际 {self.dense.dtype}")
        if self.dense.shape[1] != spec.dense_dim:
            errs.append(f"dense 维度 {self.dense.shape[1]} != 规格 {spec.dense_dim}")
        if not np.isfinite(self.dense).all():
            errs.append("dense 含 NaN/Inf")
        if self.dense.size and (self.dense.min() < -1e-6 or self.dense.max() > 1 + 1e-6):
            errs.append(f"dense 越界 [{self.dense.min():.3f}, {self.dense.max():.3f}]，应在 [0,1]")
        if self.bullets.shape[0] != n or self.bullet_mask.shape[0] != n:
            errs.append("bullets/bullet_mask 与 dense 行数不一致")
        if self.bullets.ndim != 3 or self.bullets.shape[1] != spec.n_bullets:
            errs.append(f"bullets 形状应为 (N,{spec.n_bullets},D)，实际 {self.bullets.shape}")
        if self.bullet_mask.shape != self.bullets.shape[:2]:
            errs.append("bullet_mask 形状应与 bullets 前两维一致")
        if set(np.unique(self.bullet_mask).tolist()) - {0.0, 1.0}:
            errs.append("bullet_mask 取值应为 0/1")
        if self.y.dtype.kind not in "iu":
            errs.append(f"y 应为整数，实际 {self.y.dtype}")
        if self.legal_mask is not None and self.legal_mask.shape[0] != n:
            errs.append("legal_mask 行数不一致")

        return {
            "ok": not errs,
            "errors": errs,
            "n": int(n),
            "spec_dense_dim": int(spec.dense_dim),
            "bullets": list(self.bullets.shape),
            "missing_contract_keys": [k for k in CONTRACT_KEYS if getattr(self, k) is None],
            "has_episode_id": self.match_id is not None and self.tick is not None,
            "mod_hash": self.mod_hash,
        }

    # ---------------- 覆盖率 ----------------
    def coverage_report(self, spec: ObservationSpec | None = None) -> dict:
        """逐组统计"零方差维"数量 —— 零方差 = 这批数据里该特征没带任何信息。"""
        spec = spec or ObservationSpec(include_legacy_compat=self.dense.shape[1] != 153)
        off = spec.field_offsets
        groups = {
            "self": (off["self_hp"], spec.player_dim),
            "opp": (off["opp_hp"], spec.player_dim),
            "relative": (off["dx"], spec.relative_dim),
            "cards": (off["hand_count"], spec.card_dim),
            "skills": (off["skill_level_0"], spec.skill_dim),
            "char_levels": (off["fan_level"], spec.char_level_dim),
            "weather": (off["weather_active_0"], spec.weather_dim),
            "context": (off["round_index"], spec.context_dim),
        }
        if spec.include_legacy_compat:
            groups["legacy_compat"] = (off["legacy_adx"], spec.legacy_compat_dim)

        out: dict[str, dict] = {}
        for name, (start, dim) in groups.items():
            block = self.dense[:, start:start + dim]
            var = block.var(axis=0) if len(block) else np.zeros(dim)
            out[name] = {"dim": int(dim), "nonzero_variance_dims": int((var > 1e-12).sum()),
                         "informative_ratio": float((var > 1e-12).mean()) if dim else 0.0}
        bmask = self.bullet_mask
        out["bullets"] = {
            "dim": int(self.bullets.shape[1] * self.bullets.shape[2]),
            "objects_present": int(bmask.sum()),
            "mean_objects_per_row": float(bmask.sum(axis=1).mean()) if len(bmask) else 0.0,
        }
        total_informative = sum(v.get("nonzero_variance_dims", 0) for v in out.values()
                                if "nonzero_variance_dims" in v)
        return {"groups": out, "total_informative_dims": int(total_informative),
                "dense_dim": int(spec.dense_dim),
                "note": "informative_ratio=0 的组表示该组在本批数据里完全没信息（采集缺失），"
                        "不是模型问题"}

    # ---------------- 落盘 ----------------
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        payload: dict[str, np.ndarray] = {
            "dense": self.dense, "bullets": self.bullets,
            "bullet_mask": self.bullet_mask, "y": self.y,
        }
        for k in ("match_id", "tick", "prev_macro", "legal_mask", "outcome"):
            v = getattr(self, k)
            if v is not None:
                payload[k] = v
        tmp = path + ".tmp.npz"
        np.savez(tmp, **payload)
        os.replace(tmp, path)                      # 原子落盘（前序项目 P0-5 教训）
        if self.mod_hash or self.meta:
            with open(path + ".meta.json", "w", encoding="utf-8") as f:
                json.dump({"mod_hash": self.mod_hash, **self.meta}, f,
                          indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Xv2":
        with np.load(path, allow_pickle=False) as z:
            keys = set(z.files)
            missing = [k for k in REQUIRED_KEYS if k not in keys]
            if missing:
                raise ValueError(f"X_v2 缺必需键 {missing}；已有 {sorted(keys)}")
            kw = {k: z[k] for k in REQUIRED_KEYS}
            for k in OPTIONAL_KEYS:
                if k in keys and k != "mod_hash":
                    kw[k] = z[k]
        meta = {}
        mp = path + ".meta.json"
        if os.path.exists(mp):
            meta = json.load(open(mp, encoding="utf-8"))
        kw["mod_hash"] = meta.pop("mod_hash", None)
        kw["meta"] = meta
        return cls(**kw)


# --------------------------------------------------------------------------
# 旧数据迁移（迁移期 A/B 专用）
# --------------------------------------------------------------------------
def from_legacy_11(
    X: np.ndarray, Y: np.ndarray, spec: ObservationSpec,
    train_idx: np.ndarray | None = None, char: str | None = None,
    match_id: np.ndarray | None = None, tick: np.ndarray | None = None,
) -> Xv2:
    """把旧 11 维档搬进 v2 容器（信息量不变，仅供迁移期公平对照）。

    做法：11 维在（训练切分上）做 min-max 归一化后写入 `legacy_compat` 兼容块，
    其余 153 维与弹幕集合**保持为零** —— 并由 `coverage_report` 明确报出
    "164 维里只有 11 维带信息"，杜绝"看起来很大其实空的"错觉。

    注意：`prev_macro`（旧第 3 列）**不写入任何特征位**，它在新容器里如果存在，
    语义就是"上一拍宏 ID"这一独立字段，绝不再当特征用。
    """
    if not spec.include_legacy_compat:
        raise ValueError("请用 ObservationSpec(include_legacy_compat=True)")
    if X.shape[1] != N_FEATURES:
        raise ValueError(f"期望旧 11 维输入，实际 {X.shape[1]} 维；"
                         f"列序见 constants.FEATURE_NAMES {FEATURE_NAMES}")
    n = X.shape[0]
    sub = np.arange(n) if train_idx is None else np.asarray(train_idx)
    lo = X[sub].min(axis=0)
    hi = X[sub].max(axis=0)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)
    scaled = np.clip((X - lo) / span, 0.0, 1.0).astype(np.float32)

    off = spec.field_offsets
    dense = np.zeros((n, spec.dense_dim), dtype=np.float32)
    start = off["legacy_adx"]
    dense[:, start:start + len(LEGACY_COMPAT_FIELDS)] = scaled

    return Xv2(
        dense=dense,
        bullets=np.zeros((n, spec.n_bullets, spec.bullet_dim), dtype=np.float32),
        bullet_mask=np.zeros((n, spec.n_bullets), dtype=np.float32),
        y=np.asarray(Y, dtype=np.int64),
        match_id=match_id, tick=tick,
        mod_hash="legacy11",
        meta={"char": char, "source": "from_legacy_11",
              "legacy_scaler": {"min": lo.tolist(), "span": span.tolist()},
              "macro_count_expected": MACRO_COUNT.get(char) if char else None},
    )


__all__ = ["Xv2", "REQUIRED_KEYS", "OPTIONAL_KEYS", "CONTRACT_KEYS", "from_legacy_11"]
