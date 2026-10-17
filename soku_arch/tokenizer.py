# -*- coding: utf-8 -*-
"""SokuTokenizer —— 从零自建的领域分词器（不依赖 transformers / sentencepiece）。

设计动机（LLM 为根基的关键一环）：
  对局状态是**异构表格数字**，动作是**离散宏**。要把它送进语言模型，必须先有
  一套把"局面"变成 token 序列、再变回来的**可逆**词表。本项目自建该词表，
  使模型、训练、采样、导出共用同一个符号系统（避免"训练与部署 token 不同源"）。

序列格式（positional 精简版，默认）：
    <bos> [<goal:TAG>] <state> t0 t1 ... t(F-1) <act> M_k <eos>
    长度 = 1 + (goal?1:0) + 1 + F + 1 + 1 + 1 = F + 4 (+goal)

  * t_i  = 第 i 个特征的分位分箱 token（分箱边界只用训练集拟合，落盘复用）
  * M_k  = 宏 token（动作空间）
  * <goal:TAG> = 可选的自然语言式目标提示，实现"提示词条件化策略"
    —— 这是 LLM 范式相对 MLP 的**原生优势**：同一局面下用提示切换行为倾向。

verbose_fields=True 时在每列前插入字段名 token，便于人读与调试（长度 F*2+4）。

反序列化：`decode_action` 从 <act> 后的位置取宏 ID；`legal_macro_ids` 供
受限解码（只允许合法宏 token）使用。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

SPECIALS: tuple[str, ...] = ("<pad>", "<unk>", "<bos>", "<eos>", "<state>", "<act>")

# 目标提示集合：与 standard_tree.py 的教义类别对齐（远/中/近/贴身/地被空/空对空/角/受攻）
DEFAULT_GOALS: tuple[str, ...] = (
    "neutral", "rush", "zone", "defend", "punish", "escape", "corner", "anti_air",
)


@dataclass
class TokenizerConfig:
    n_features: int = 11
    n_macros: int = 55
    n_bins: int = 16
    verbose_fields: bool = False
    goals: tuple[str, ...] = DEFAULT_GOALS
    # emit_bins=False：序列里不再逐维放分箱 token，只保留 <state> 标记。
    # 用于"观测走软前缀"的架构：全面观测由 ObservationEncoder 压成连续 token，
    # 分箱 token 变成冗余，而 token 数是与参数量同量级的成本项（实测 T=128 时
    # 2M 参数已 94.8ms），必须省掉。
    emit_bins: bool = True


@dataclass
class SokuTokenizer:
    cfg: TokenizerConfig = field(default_factory=TokenizerConfig)
    feature_names: tuple[str, ...] = ()
    edges: np.ndarray | None = None          # (n_features, n_bins-1) 分位分箱边界
    _vocab: dict[str, int] = field(default_factory=dict, init=False)
    _inv: list[str] = field(default_factory=list, init=False)

    # ---------------- 词表构建 ----------------
    def __post_init__(self) -> None:
        if not self.feature_names:
            self.feature_names = tuple(f"f{i}" for i in range(self.cfg.n_features))
        self._build_vocab()

    def _add(self, tok: str) -> int:
        if tok not in self._vocab:
            self._vocab[tok] = len(self._inv)
            self._inv.append(tok)
        return self._vocab[tok]

    def _build_vocab(self) -> None:
        self._vocab, self._inv = {}, []
        for t in SPECIALS:
            self._add(t)
        for g in self.cfg.goals:
            self._add(f"<goal:{g}>")
        if self.cfg.verbose_fields:
            for name in self.feature_names:
                self._add(f"<f:{name}>")
        self._bin_base = len(self._inv)
        for i in range(self.cfg.n_features):
            for b in range(self.cfg.n_bins):
                self._add(f"<v{i}:{b}>")
        self._macro_base = len(self._inv)
        for k in range(self.cfg.n_macros):
            self._add(f"<m{k}>")
        self._macro_end = len(self._inv)

    # ---------------- 属性 ----------------
    @property
    def pad_id(self) -> int: return self._vocab["<pad>"]
    @property
    def unk_id(self) -> int: return self._vocab["<unk>"]
    @property
    def bos_id(self) -> int: return self._vocab["<bos>"]
    @property
    def eos_id(self) -> int: return self._vocab["<eos>"]
    @property
    def state_id(self) -> int: return self._vocab["<state>"]
    @property
    def act_id(self) -> int: return self._vocab["<act>"]

    @property
    def vocab_size(self) -> int: return len(self._inv)

    @property
    def macro_range(self) -> tuple[int, int]: return (self._macro_base, self._macro_end)

    def macro_token(self, k: int) -> int: return self._macro_base + int(k)

    def token_to_macro(self, tid: int) -> int:
        if not (self._macro_base <= tid < self._macro_end):
            raise ValueError(f"token {tid} 不是宏 token")
        return tid - self._macro_base

    def goal_token(self, goal: str) -> int:
        key = f"<goal:{goal}>"
        if key not in self._vocab:
            raise KeyError(f"未知 goal: {goal}")
        return self._vocab[key]

    # ---------------- 分箱拟合 ----------------
    def fit_bins(self, X: np.ndarray) -> "SokuTokenizer":
        """在**训练集**上按分位拟合分箱边界（只用训练集，避免统计泄漏）。"""
        X = np.asarray(X, dtype=np.float64)
        n_feat = min(self.cfg.n_features, X.shape[1])
        nb = self.cfg.n_bins
        edges = np.zeros((n_feat, max(0, nb - 1)), dtype=np.float64)
        for i in range(n_feat):
            col = X[:, i]
            col = col[np.isfinite(col)]
            if col.size == 0:
                continue
            qs = np.linspace(0, 100, nb + 1)[1:-1]
            e = np.unique(np.percentile(col, qs))
            # 唯一边少于 nb-1（离散/常量列）时右填充，保证 bin 索引不越界
            if e.size < nb - 1:
                pad = np.full(nb - 1 - e.size, e[-1] if e.size else 0.0)
                e = np.concatenate([e, pad])
            edges[i] = e[: nb - 1]
        self.edges = edges
        return self

    def bin_of(self, i: int, value: float) -> int:
        if self.edges is None:
            raise RuntimeError("未 fit_bins")
        if not np.isfinite(value):
            return 0
        return int(np.searchsorted(self.edges[i], value, side="right"))

    def bin_token(self, i: int, value: float) -> int:
        return self._bin_base + i * self.cfg.n_bins + self.bin_of(i, value)

    def token_to_bin(self, tid: int) -> tuple[int, int] | None:
        """分箱 token -> (特征列, 箱号)；非分箱 token 返回 None。"""
        off = int(tid) - self._bin_base
        span = self.cfg.n_features * self.cfg.n_bins
        if not (0 <= off < span):
            return None
        return divmod(off, self.cfg.n_bins)

    def bin_center(self, i: int, b: int) -> float:
        """分箱代表值（反序列化/状态生成时用）。"""
        if self.edges is None:
            return float(b)
        e = self.edges[i]
        lo = -np.inf if b == 0 else e[b - 1]
        hi = np.inf if b >= len(e) else e[b]
        if not np.isfinite(lo) and not np.isfinite(hi):
            return 0.0
        if not np.isfinite(lo):
            return float(hi)
        if not np.isfinite(hi):
            return float(lo)
        return float((lo + hi) / 2.0)

    # ---------------- 编解码 ----------------
    def _state_token_count(self) -> int:
        """<state> 之后、<act> 之前的 token 数。"""
        if not self.cfg.emit_bins:
            return 0
        return self.cfg.n_features * (2 if self.cfg.verbose_fields else 1)

    def encode_row(self, feats: np.ndarray, macro: int, goal: str | None = None) -> tuple[list[int], list[int]]:
        """返回 (ids, loss_mask)；loss_mask 只在宏 token 上为 1（动作位监督）。

        emit_bins=False 时：序列为 <bos> [goal] <state> <act> <mK> <eos>（5~6 个 token），
        观测信息由 ObservationEncoder 以软前缀形式注入，而非逐维分箱 token。
        """
        ids = [self.bos_id]
        mask = [0]
        if goal is not None:
            ids.append(self.goal_token(goal)); mask.append(0)
        ids.append(self.state_id); mask.append(0)
        if self.cfg.emit_bins:
            f = np.asarray(feats, dtype=np.float64).reshape(-1)
            for i in range(self.cfg.n_features):
                if self.cfg.verbose_fields:
                    ids.append(self._vocab[f"<f:{self.feature_names[i]}>"]); mask.append(0)
                ids.append(self.bin_token(i, float(f[i]) if i < f.size else float("nan")))
                mask.append(0)
        ids.append(self.act_id); mask.append(0)
        ids.append(self.macro_token(macro)); mask.append(1)
        ids.append(self.eos_id); mask.append(0)
        return ids, mask

    def action_position(self, seq_len: int, has_goal: bool = False) -> int:
        """宏 token 在序列中的下标（= 需要采样/监督的位置）。

        emit_bins=True : <bos> [goal] <state> t0..t(F-1) <act> <mK> <eos>
        emit_bins=False: <bos> [goal] <state> <act> <mK> <eos>
        注意：使用软前缀时（ObsConditionedLM），真实下标还要再加 n_soft。
        """
        return 1 + (1 if has_goal else 0) + 1 + self._state_token_count() + 1

    def decode_action(self, ids: list[int], has_goal: bool = False) -> int | None:
        pos = self.action_position(len(ids), has_goal)
        if 0 <= pos < len(ids) and self._macro_base <= ids[pos] < self._macro_end:
            return self.token_to_macro(ids[pos])
        for tid in ids:
            if self._macro_base <= tid < self._macro_end:
                return self.token_to_macro(tid)
        return None

    def legal_macro_ids(self, legal: np.ndarray) -> list[int]:
        return [self.macro_token(k) for k in np.flatnonzero(legal)]

    # ---------------- 持久化 ----------------
    def to_json(self) -> dict:
        return {
            "cfg": {**self.cfg.__dict__, "goals": list(self.cfg.goals)},
            "feature_names": list(self.feature_names),
            "edges": None if self.edges is None else self.edges.tolist(),
            "vocab": self._vocab,
            "vocab_size": self.vocab_size,
            "macro_range": list(self.macro_range),
            "bin_base": self._bin_base,
        }

    @classmethod
    def from_json(cls, d: dict) -> "SokuTokenizer":
        cfg = TokenizerConfig(**d["cfg"])
        tok = cls(cfg=cfg, feature_names=tuple(d["feature_names"]))
        if d.get("edges") is not None:
            tok.edges = np.asarray(d["edges"], dtype=np.float64)
        # 词表顺序在 __post_init__ 里是确定性的，若不一致则说明配置漂移 -> 大声失败
        if tok._vocab != d["vocab"]:
            raise ValueError("tokenizer 词表与存档不一致（配置漂移，禁止静默加载）")
        return tok

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "SokuTokenizer":
        with open(path, encoding="utf-8") as f:
            return cls.from_json(json.load(f))


__all__ = ["SPECIALS", "DEFAULT_GOALS", "TokenizerConfig", "SokuTokenizer"]
