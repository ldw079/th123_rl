# -*- coding: utf-8 -*-
"""数据集层：加载、体检、切分、torch Dataset。

核心设计决定（每条都有证据）：

A. 切分方式默认 "block"（时间块），而不是前序项目 train_bc.py:50-52 的随机逐行切分。
   理由：本数据是"按批追加、批内时间有序"（train_tm.py:844 concatenate），
   相邻行高度相关；随机切分会让验证集与训练集共享同一局的邻居 -> 乐观偏差。
   由于磁盘数据【没有 match_id】，无法做真正的局级分组切分；因此：
     * 默认 block 切分（更保守、更接近真实泛化）
     * 同时提供 random 切分，用于【量化泄漏幅度】：两者之差 = 泄漏估计
     * 提供 group 切分接口，一旦采集端补上 match_id 即可启用

B. 逐列标准化只在训练切分上 fit（soku_arch.schema.Standardizer）。
   理由：suika 的 spirit 列量纲与 reimu/marisa 不同（65.49 vs 1.0）。

C. 体检（health_report）显式暴露：死列、类别覆盖缺口、每列分位、标签熵、类别不均衡度。
   理由：前序项目把 11 维当特征用，其中第 3 列恒为 -1（标签载体），
   静默喂常数进网络会浪费容量并掩盖契约缺陷。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from .constants import MACRO_COUNT, N_FEATURES
from .schema import (
    COL_PREV_MACRO,
    FeatureSpec,
    KNOWN_DEAD_COLUMNS,
    dead_columns,
    validity_mask,
)

# 需要 match_id 才能做的切分；缺列时给出可执行的修复指引
MISSING_GROUP_KEY_MSG = (
    "该数据集没有 match_id/tick_index，无法做局级分组切分或时序窗口。\n"
    "修复（采集端数据契约）：distill 落盘时增加\n"
    "  match_id (N,) int32   局唯一ID\n"
    "  tick     (N,) int32   局内决策拍序号\n"
    "  prev_macro (N,) int16 真正的上一拍宏 ID（当前第3列被标签占用）\n"
    "  legal_mask (N,M) uint8 每行可选宏集合\n"
    "  outcome  (N,) int8    终局 1胜/0负/2平（价值头标签）\n"
    "见 docs/DATA_CONTRACT.md。"
)


@dataclass
class DistillSet:
    """一份 distill 数据集 + 其体检结果。"""

    char: str
    X: np.ndarray            # (N, 11) float32 原始
    Y: np.ndarray            # (N,)   int64  宏 ID
    valid: np.ndarray        # (N,)   bool
    n_macros: int
    health: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.valid.sum())


def load_distill(path: str, char: str | None = None) -> DistillSet:
    with np.load(path) as d:
        X = d["X"].astype(np.float32)
        Y = d["Y"].astype(np.int64)
    if char is None:
        base = os.path.basename(path)
        # distill_data_<char>[_exp].npz
        stem = base[len("distill_data_"):-len(".npz")] if base.startswith("distill_data_") else base
        char = stem.split("_")[0]
    n_macros = MACRO_COUNT.get(char)
    if n_macros is None:
        n_macros = int(Y.max()) + 1
    X = X[:, :N_FEATURES] if X.shape[1] > N_FEATURES else X
    ds = DistillSet(char=char, X=X, Y=Y, valid=validity_mask(X), n_macros=n_macros)
    ds.health = health_report(ds)
    return ds


def health_report(ds: DistillSet) -> dict:
    X, Y, valid = ds.X, ds.Y, ds.valid
    Xv, Yv = X[valid], Y[valid]
    dead = dead_columns(Xv)
    counts = np.bincount(Yv, minlength=ds.n_macros)
    used = np.flatnonzero(counts > 0)
    missing = [int(i) for i in range(ds.n_macros) if counts[i] == 0]
    p = counts[used] / counts.sum()
    imbalance = float(counts.max() / max(1, counts[counts > 0].min()))
    cols = {}
    for c in range(Xv.shape[1]):
        col = Xv[:, c]
        cols[c] = {
            "min": float(col.min()), "max": float(col.max()),
            "mean": float(col.mean()), "std": float(col.std()),
            "n_unique": int(len(np.unique(col))),
        }
    return {
        "char": ds.char,
        "n_rows": int(len(X)),
        "n_valid": int(valid.sum()),
        "n_dead_columns": len(dead),
        "dead_columns": [int(c) for c in dead],
        "known_dead_columns": list(KNOWN_DEAD_COLUMNS),
        "label_carrier_column_constant": bool(len(np.unique(Xv[:, COL_PREV_MACRO])) == 1),
        "n_macros": ds.n_macros,
        "n_classes_used": int(len(used)),
        "class_coverage": float(len(used) / ds.n_macros),
        "missing_macros": missing,
        "min_class_count": int(counts[counts > 0].min()) if len(used) else 0,
        "max_class_count": int(counts.max()),
        "imbalance_ratio": imbalance,
        "label_entropy": float(-(p * np.log(p)).sum()),
        "label_entropy_max": float(np.log(ds.n_macros)),
        "has_episode_id": False,
        "columns": cols,
    }


def split_indices(
    n: int, mode: str = "block", val_frac: float = 0.2, seed: int = 0,
    group: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """返回 (train_idx, val_idx)。

    mode:
      "block"  —— 尾部 val_frac 作为验证集（尊重时间顺序，无邻域泄漏）
      "random" —— 随机切分（复现前序项目的做法，用于量化泄漏）
      "group"  —— 按 group 数组分组（需 match_id；当前数据不可用）
    """
    n = int(n)
    if mode == "random":
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n)
        cut = int(n * (1.0 - val_frac))
        return perm[:cut], perm[cut:]
    if mode == "block":
        cut = int(n * (1.0 - val_frac))
        return np.arange(0, cut), np.arange(cut, n)
    if mode == "group":
        if group is None:
            raise ValueError(MISSING_GROUP_KEY_MSG)
        uniq = np.unique(group)
        rng = np.random.default_rng(seed)
        rng.shuffle(uniq)
        cut = max(1, int(len(uniq) * (1.0 - val_frac)))
        val_groups = set(uniq[cut:].tolist())
        is_val = np.array([g in val_groups for g in group])
        return np.flatnonzero(~is_val), np.flatnonzero(is_val)
    raise ValueError(f"未知切分模式: {mode}")


class MacroDataset:
    """最小 torch Dataset（避免依赖 torchvision/tensordict）。

    同时提供 numpy 视图，便于不装 torch 时做纯 numpy 基线。
    """

    def __init__(self, X: np.ndarray, Y: np.ndarray, indices: np.ndarray, spec: FeatureSpec):
        self.spec = spec
        self.y = np.asarray(Y, dtype=np.int64)[indices]
        self.x = spec.transform(np.asarray(X, dtype=np.float32)[indices])

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i: int):
        import torch

        return torch.from_numpy(self.x[i]), torch.tensor(int(self.y[i]), dtype=torch.long)

    def to_torch(self) -> tuple["object", "object"]:
        import torch

        return torch.from_numpy(self.x), torch.from_numpy(self.y)


def prepare(
    path: str, mode: str = "block", val_frac: float = 0.2, seed: int = 0,
    drop_dead: bool = True, char: str | None = None,
) -> dict:
    """一站式：加载 -> 体检 -> 切分 -> 拟合标准化 -> 返回张量。

    注意：标准化只在训练切分上 fit（防止验证集统计泄漏）。
    """
    ds = load_distill(path, char=char)
    Xv, Yv = ds.X[ds.valid], ds.Y[ds.valid]
    n = len(Yv)
    tr, va = split_indices(n, mode=mode, val_frac=val_frac, seed=seed)

    columns = tuple(range(Xv.shape[1]))
    dropped: tuple[int, ...] = ()
    if drop_dead:
        dead = tuple(sorted(set(dead_columns(Xv[tr])) | set(KNOWN_DEAD_COLUMNS)))
        dropped = dead
        columns = tuple(c for c in columns if c not in dead)

    spec = FeatureSpec(columns=columns, dropped=dropped)
    spec.std.fit(Xv[tr][:, columns])
    return {
        "char": ds.char,
        "health": ds.health,
        "spec": spec,
        "train": MacroDataset(Xv, Yv, tr, spec),
        "val": MacroDataset(Xv, Yv, va, spec),
        "n_macros": ds.n_macros,
        "split_mode": mode,
        "n_train": len(tr),
        "n_val": len(va),
    }


__all__ = [
    "DistillSet", "load_distill", "health_report", "split_indices",
    "MacroDataset", "prepare", "MISSING_GROUP_KEY_MSG",
]
