# -*- coding: utf-8 -*-
"""观测 schema：有效性、归一化、合法性掩码。

设计要点（全部由证据驱动，见注释引用）：

1. 归一化统计量只能【在训练集上拟合】，不能写死。
   证据：distill_data_suika.npz 的 spirit 列 max=65.49，而 reimu/marisa 为 1.0
   （train_tm.py:719 写的是 left["spirit"]/1000.0，量纲本应一致）。
   -> 落盘文件的列量纲跨角色不一致，说明磁盘数据来自不同版本的产出代码。
   -> 结论：用写死常数做归一化会在 suika 上产生 65 倍尺度错误。
   因此 Standardizer 只在训练切分上 fit，并落盘供推理复用。

2. 第 3 列恒为 -1（n_uniq=1，全部 20 万行）。**这是设计结果，不是 bug**：
   train_tm.py:838-840 把 mid 写进该列 -> 取出作为标签 Y -> 再把该列原地清成 -1.0。
   即该列是【标签载体】。但 distill.py:23 / standard_tree.py:26 / train_tm.py:499
   三处文档把它记为特征（"上宏ID"/"macro_id"），与代码相反。
   -> 结论：该列永远不能当特征用；文档需纠正。本模块把它列进 KNOWN_DEAD_COLUMNS，
      并在数据体检报告里显式暴露，避免"悄悄喂一个常数进网络"。

3. 有效性掩码：distill.py:36 用 X[:,0] >= 0（adx 非负）。当前三个文件 100% 有效。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .constants import (
    FEATURE_INVALID_SENTINEL,
    FEATURE_NAMES,
    N_FEATURES,
    TTI_NO_THREAT,
    LEGALITY_RULES,
    MACRO_COUNT,
)

COL_ADX = 0
COL_SPIRIT = 1
COL_CLOSE = 2
COL_PREV_MACRO = 3
COL_GAME_FRAME = 4
COL_DY = 5
COL_OPP_AIR = 6
COL_BULLET_NEAR = 7
COL_I_AM_LEFT = 8
COL_TTI = 9
COL_OPP_CORNER = 10

# 已知"死列"：在当前数据集上恒为常数，携带 0 信息量。
KNOWN_DEAD_COLUMNS: tuple[int, ...] = (COL_PREV_MACRO,)


def validity_mask(X: np.ndarray) -> np.ndarray:
    """官方有效性掩码：distill.py:36 `use = X[:, 0] >= 0`。"""
    return X[:, COL_ADX] >= 0.0


def dead_columns(X: np.ndarray, atol: float = 0.0) -> list[int]:
    """返回在给定数据上取值恒定的列（无信息量）。

    用于在训练前把"死特征"显式暴露出来，而不是让模型把常数喂进网络。
    """
    out = []
    for c in range(X.shape[1]):
        col = X[:, c]
        if np.nanmax(col) - np.nanmin(col) <= atol:
            out.append(c)
    return out


@dataclass
class Standardizer:
    """按列 z-score / 稳健缩放，只在训练集上 fit。

    * 对取值恒定的列：scale 记为 1.0，避免除零；这些列应在上游被 drop。
    * 对含 NaN/Inf 的列：用训练集中位数填补。
    """

    loc: np.ndarray | None = None
    scale: np.ndarray | None = None
    fill: np.ndarray | None = None
    clip: float = 8.0

    def fit(self, X: np.ndarray) -> "Standardizer":
        X = np.asarray(X, dtype=np.float64)
        self.fill = np.nanmedian(np.where(np.isfinite(X), X, np.nan), axis=0)
        self.fill = np.where(np.isfinite(self.fill), self.fill, 0.0)
        Xc = np.where(np.isfinite(X), X, self.fill)
        self.loc = Xc.mean(axis=0)
        scale = Xc.std(axis=0)
        self.scale = np.where(scale < 1e-8, 1.0, scale)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.loc is None or self.scale is None or self.fill is None:
            raise RuntimeError("Standardizer 未 fit")
        X = np.asarray(X, dtype=np.float32)
        Xc = np.where(np.isfinite(X), X, self.fill.astype(np.float32))
        Z = (Xc - self.loc.astype(np.float32)) / self.scale.astype(np.float32)
        return np.clip(Z, -self.clip, self.clip).astype(np.float32)

    def state_dict(self) -> dict[str, np.ndarray]:
        return {"loc": self.loc, "scale": self.scale, "fill": self.fill}

    @classmethod
    def from_state_dict(cls, d: dict[str, np.ndarray]) -> "Standardizer":
        s = cls()
        s.loc, s.scale, s.fill = d["loc"], d["scale"], d["fill"]
        return s


@dataclass
class FeatureSpec:
    """一次训练/推理使用的特征列定义（可裁剪，保证训练与部署同源）。"""

    columns: tuple[int, ...] = tuple(range(N_FEATURES))
    dropped: tuple[int, ...] = ()
    std: Standardizer = field(default_factory=Standardizer)

    @property
    def dim(self) -> int:
        return len(self.columns)

    def names(self) -> tuple[str, ...]:
        return tuple(FEATURE_NAMES[c] for c in self.columns)

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.std.fit(X[:, self.columns])
        return self.std.transform(X[:, self.columns])

    def transform(self, X: np.ndarray) -> np.ndarray:
        return self.std.transform(X[:, self.columns])

    def to_json(self) -> dict:
        return {
            "columns": [int(c) for c in self.columns],
            "column_names": list(self.names()),
            "dropped": [int(c) for c in self.dropped],
            "standardizer": {k: v.tolist() for k, v in self.std.state_dict().items()},
        }


# --------------------------------------------------------------------------
# 合法性掩码
# --------------------------------------------------------------------------
def legality_mask(
    features: np.ndarray,
    macro_names: Sequence[str],
    *,
    rules: dict | None = None,
) -> np.ndarray:
    """返回 bool 数组，True = 该宏在当前观测下**允许**选择。

    仅使用 11 维特征里**真实存在**的判据；无法判定的条件一律不掩（宁可放开也不要错杀，
    因为错杀会产生"永远学不到"的死动作 —— 前序项目 1.9 死招事故的同类风险）。

    当前可实现：
      * opp_corner=0 时禁"版边连A"（该宏语义要求对手在版边）
      * opp_air=0   时禁"空连A"（该宏语义要求对手在空中）
      * bullet_near=0 时不禁弹幕宏（远程布置弹幕是正解，见 standard_tree.py r3/39）
    TO_VERIFY / 缺失特征导致**无法**实现：
      * 符卡类宏（卡·xx）：需要 cardGauge / 手牌，11 维里没有 -> 不掩码
      * 空中宏（jA/j6A/j2A/...）：需要"我是否在空中"，11 维里只有 opp_air -> 不掩码
      * 结界/无敌宏：需要灵力与受击状态 -> 不掩码
    """
    rules = LEGALITY_RULES if rules is None else rules
    f = np.asarray(features, dtype=np.float64).reshape(-1)
    mask = np.ones(len(macro_names), dtype=bool)

    # 规则用【语义子串】匹配宏名（如 "版边" 命中 "版边连A"），
    # 这样同一份规则可同时适配灵梦/魔理沙/萃香三套宏库，无需硬编码各库 ID。
    for sub, cond_col, cond_val in rules.get("require", []):
        for idx, mn in enumerate(macro_names):
            if sub in mn and f[cond_col] != cond_val:
                mask[idx] = False
    return mask


def mask_stats(
    X: np.ndarray, Y: np.ndarray, macro_names: Sequence[str]
) -> dict[str, int]:
    """统计被掩码"错杀"的样本数：若某宏被掩，但训练集里它被选中过，说明掩码过严。"""
    killed = 0
    total = 0
    for i in range(len(X)):
        m = legality_mask(X[i], macro_names)
        total += 1
        if not m[Y[i]]:
            killed += 1
    return {"total": total, "would_kill": killed}


__all__ = [
    "COL_ADX", "COL_SPIRIT", "COL_CLOSE", "COL_PREV_MACRO", "COL_GAME_FRAME",
    "COL_DY", "COL_OPP_AIR", "COL_BULLET_NEAR", "COL_I_AM_LEFT", "COL_TTI",
    "COL_OPP_CORNER", "KNOWN_DEAD_COLUMNS",
    "validity_mask", "dead_columns", "Standardizer", "FeatureSpec",
    "legality_mask", "mask_stats",
]
