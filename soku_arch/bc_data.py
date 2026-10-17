# -*- coding: utf-8 -*-
"""帧级 BC 数据层：把 `tools/rep_drive.py --bulk` 的分片变成可训练的 (观测, 144 动作) 行。

设计要点（每条都对应 docs/STATUS.md §2 里点名的陷阱）：

1. **1 帧对齐**（陷阱 1）。驱动循环是"先发输入 `inp[i]`，再收状态 `x[i]`"，
   而 `inp[0] = -1`（占位）。两种配对都实现，并**都实测**：
     * `lag1`（默认）：`obs = x[i-1]`，`label = inp[i]`。
       这是**部署时唯一可用**的配对 —— 在线迭代 i 上，智能体此刻只知道 `x[1..i-1]`，
       要吐出的就是 `inp[i]`。所以它是正确性上的默认，不是调参选出来的。
     * `lag0`：`obs = x[i]`，`label = inp[i]`（"状态与同拍输入对齐"的朴素读法）。
   两者之差 = 这条歧义对精度的影响，报告里逐项给出。
2. **回合边界**（陷阱 2）。`meta.round_end_frames_*` 标出得分帧；得分帧之后的
   回放演出段不是有效战斗局面，按 `play_mask` 切掉（`rounds="auto"` 用"血量单帧
   回升 ≥3000"定位新回合开始帧，找不到就切到片尾）。绝不让"重置"混进训练集。
3. **score 列**（陷阱 3）。默认 `score_mode="drop"`（见 frame_obs）。
4. **极不平衡**（陷阱 4）。这里只**统计并暴露**分布；加权在训练侧
   （`losses.make_class_weights`，inverse-sqrt）。
5. **上一拍输入必须进观测**（本次实测新增，见 `frame_obs.prev_block` 的长注释）。
   非想天则的按键常被按住几十帧，"照抄上一拍"这条零参数基线 top1 = **0.8751**（验证集）；
   不含该信息的逐帧观测器只有 0.33–0.34（且越训越差）。因此 `prev_mode` 默认打开
   （`joint`），并用持久性基线做硬门槛 —— 注意**门槛不是多数类（0.319）**。

切分：一个分片 = 一局（天然 `match_id`）。
  * 分片 ≥2 时用 `split="group"` 做**局级**切分（无邻域泄漏，最保守）；
  * 只有 1 个分片时 `group` **明确报错**，改用 `split="block"`（按时间尾巴留出）。
    行序被构造成"帧优先、两侧次之"，因此 block 切分的验证集同时含左右两侧。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from .dataset import split_indices
from .frame_obs import (
    N_SIDE_COLS,
    SIDE_COLS,
    ObservationSpec,
    prev_block,
    prev_extra_dim,
    vectorize_frames,
)
from .input_codec import ACTION_SPACE_SIZE, BattleInput

IGNORE_INDEX = -100
HP_RESET_JUMP = 3000.0        # 回合重置的"单帧血量回升"阈值（见 play_mask）
ALIGNMENTS = ("lag1", "lag0")

DIR_NAMES = ("1", "2", "3", "4", "5", "6", "7", "8", "9")   # numpad，5=中立
BTN_NAMES = ("A", "B", "C", "dash")
COMBINED_BITS = ("AandB", "BandC", "pause", "select")       # 144 空间**装不下**的位


# ---------------------------------------------------------------------------
# 分片加载
# ---------------------------------------------------------------------------
@dataclass
class FrameShard:
    """一局的分片（= 一个 match）。"""

    path: str
    name: str
    x: np.ndarray                 # (N, 20)
    hand: np.ndarray              # (N, 2, 5)
    inp: np.ndarray               # (N, 2) 原始 u16 BattleKeys，-1 = 无
    meta: dict = field(default_factory=dict)
    side_cols: tuple[str, ...] = SIDE_COLS
    bullet: np.ndarray | None = None
    bullet_mask: np.ndarray | None = None

    @property
    def frames(self) -> int:
        return int(self.x.shape[0])

    @property
    def match_id(self) -> str:
        return self.meta.get("file", self.name)

    def validation(self) -> dict:
        errs: list[str] = []
        if self.x.ndim != 2 or self.x.shape[1] != 2 * N_SIDE_COLS:
            errs.append(f"x 形状 {self.x.shape} 应为 (N,{2 * N_SIDE_COLS})")
        if self.hand.shape != (self.frames, 2, 5):
            errs.append(f"hand 形状 {self.hand.shape} 应为 (N,2,5)")
        if self.inp.shape != (self.frames, 2):
            errs.append(f"inp 形状 {self.inp.shape} 应为 (N,2)")
        if self.side_cols != SIDE_COLS:
            errs.append(f"side_cols={self.side_cols} 与本工具约定的 {SIDE_COLS} 不一致")
        return {"ok": not errs, "errors": errs, "frames": self.frames,
                "file": self.meta.get("file", self.name)}


def load_shard(path: str) -> FrameShard:
    """加载单个分片；缺列/形状不符**大声失败**（不做静默降级）。"""
    with np.load(path, allow_pickle=True) as z:
        keys = set(z.files)
        missing = [k for k in ("x", "hand", "inp") if k not in keys]
        if missing:
            raise ValueError(f"分片 {path} 缺必需键 {missing}；已有 {sorted(keys)}")
        x = z["x"].astype(np.float32)
        hand = z["hand"].astype(np.int16)
        inp = z["inp"].astype(np.int32)
        side_cols = tuple(str(s) for s in z["side_cols"].tolist()) if "side_cols" in keys \
            else SIDE_COLS
        meta = {}
        if "meta" in keys:
            raw = z["meta"]
            txt = str(raw.item()) if raw.dtype.kind in "US" and raw.shape == () else str(raw)
            try:
                meta = json.loads(txt)
            except json.JSONDecodeError:
                meta = {"raw": txt}
        bullet = z["bullet"].astype(np.float32) if "bullet" in keys else None
        bmask = z["bullet_mask"].astype(np.float32) if "bullet_mask" in keys else None
    sh = FrameShard(path=path, name=os.path.basename(path), x=x, hand=hand, inp=inp,
                    meta=meta, side_cols=side_cols, bullet=bullet, bullet_mask=bmask)
    v = sh.validation()
    if not v["ok"]:
        raise ValueError(f"分片校验失败 {path}: {v['errors']}")
    return sh


def discover_shards(root: str) -> list[str]:
    """`root` 可以是分片目录本身，也可以是 `--bulk --out` 的根（自动进 shards/）。"""
    if os.path.isfile(root):
        return [root]
    cand = os.path.join(root, "shards")
    d = cand if os.path.isdir(cand) else root
    if not os.path.isdir(d):
        raise FileNotFoundError(f"找不到分片目录: {root}")
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".npz")]


# ---------------------------------------------------------------------------
# 标签：原始 u16 → 144 联合动作
# ---------------------------------------------------------------------------
def joint_labels(raw_inp: np.ndarray) -> np.ndarray:
    """(N,) 原始 BattleKeys（-1 表示占位）→ (N,) int64 联合动作下标，非法/占位为 -100。

    144 = 9 方向 × 16 按键掩码（A/B/C/dash）。`AandB`/`BandC`/`pause`/`select`
    这四个位**装不进**该空间，这里的丢失量由 `label_report` 显式统计，不静默丢弃。
    """
    raw = np.asarray(raw_inp).reshape(-1)
    out = np.full(raw.shape[0], IGNORE_INDEX, dtype=np.int64)
    for i, v in enumerate(raw):
        v = int(v)
        if v < 0:
            continue
        out[i] = BattleInput(v).joint_index
    return out


def label_report(raw_inp: np.ndarray) -> dict:
    """标签质量审计：不可映射位出现率（= 144 动作空间的信息损失）。"""
    raw = np.asarray(raw_inp).reshape(-1)
    valid = raw[raw >= 0]
    n = int(valid.size)
    counts = {b: 0 for b in COMBINED_BITS}
    for v in valid:
        d = BattleInput(int(v)).as_dict()
        for b in COMBINED_BITS:
            counts[b] += int(bool(d[b]))
    # 方向同时按相反键 → BattleInput.hv 取差值为 0（中立），这是规范化而非丢弃
    both_h = int(np.sum(((valid >> 2) & 1).astype(bool) & ((valid >> 3) & 1).astype(bool)))
    both_v = int(np.sum(((valid >> 0) & 1).astype(bool) & ((valid >> 1) & 1).astype(bool)))
    return {
        "n_valid_frames": n,
        "n_placeholder": int((raw < 0).sum()),
        "unmappable_bit_hits": counts,
        "unmappable_rate": (sum(counts.values()) / n) if n else 0.0,
        "opposite_dir_both_pressed": {"horizontal": both_h, "vertical": both_v,
                                      "rate": ((both_h + both_v) / n) if n else 0.0},
        "note": "unmappable_rate 是 144 动作空间的**已量化信息损失**；"
                "opposite_dir 同时按下按 BattleInput.hv 规范化为中立（TO_VERIFY，见 input_codec）。",
    }


def _prev_inputs(raw_col: np.ndarray, label_idx: np.ndarray) -> np.ndarray:
    """label 帧的**上一拍原始输入**，用前向填充跨过 `-1` 占位帧。

    `-1` 有两种来源：(a) 第 0 帧的占位；(b) 喂入闸门暂停期间我们"保持上一次输入"
        而记下的占位 —— 后者游戏里实际按住的仍是最后一次真输入，所以必须填充。
    """
    raw_col = np.asarray(raw_col).reshape(-1)
    n = raw_col.shape[0]
    valid_idx = np.where(raw_col >= 0, np.arange(n), -1)
    last = np.maximum.accumulate(valid_idx)          # <=k 的最后一个有效下标
    filled = np.where(last >= 0, raw_col[np.maximum(last, 0)], -1)
    prev = filled[np.maximum(np.asarray(label_idx) - 1, 0)]
    return np.where(np.asarray(label_idx) >= 1, prev, -1)


def action_name(joint: int) -> str:
    d, m = divmod(int(joint), 16)
    btns = "+".join(BTN_NAMES[i] for i in range(4) if m >> i & 1) or "-"
    return f"dir{DIR_NAMES[d]}/{btns}"


def distribution_report(y: np.ndarray, n_classes: int = ACTION_SPACE_SIZE) -> dict:
    """类别分布（用于论证"必须加权/分层采样"）。"""
    y = np.asarray(y)
    y = y[y >= 0]
    counts = np.bincount(y, minlength=n_classes)
    used = np.flatnonzero(counts > 0)
    top = np.argsort(-counts)[:10]
    dirs = np.bincount(y // 16, minlength=9)
    masks = np.bincount(y % 16, minlength=16)
    p = counts[used] / max(1, counts.sum())
    entropy = float(-(p * np.log(np.maximum(p, 1e-12))).sum())
    return {
        "n": int(y.size),
        "n_classes_total": int(n_classes),
        "n_classes_used": int(used.size),
        "class_coverage": float(used.size / n_classes),
        "majority_class": int(counts.argmax()),
        "majority_name": action_name(int(counts.argmax())),
        "majority_share": float(counts.max() / max(1, y.size)),
        "imbalance_ratio": float(counts.max() / max(1, counts[used].min())) if used.size else 0.0,
        "entropy_nats": entropy,
        "neutral_share": float(counts[64] / max(1, y.size)),   # dir=5, mask=0
        "any_button_share": float(1.0 - counts[[d * 16 for d in range(9)]].sum() / max(1, y.size)),
        "direction_counts": {DIR_NAMES[i]: int(c) for i, c in enumerate(dirs)},
        "button_mask_counts": {f"{m:04b}": int(c) for m, c in enumerate(masks) if c},
        "top10": [{"joint": int(c), "name": action_name(int(c)), "count": int(counts[c]),
                   "share": float(counts[c] / max(1, y.size))} for c in top if counts[c] > 0],
    }


# ---------------------------------------------------------------------------
# 对齐 / 回合切段
# ---------------------------------------------------------------------------
def alignment_pairs(n: int, align: str) -> tuple[np.ndarray, np.ndarray]:
    """返回 (obs_frame_idx, label_frame_idx)，长度 n-1（第 0 帧的 inp 是 -1 占位）。

    lag1: (i-1, i)  —— 部署可用（看到 x[i-1] 后决定 inp[i]）
    lag0: (i, i)    —— 朴素同拍对齐
    """
    if align not in ALIGNMENTS:
        raise ValueError(f"align 只能是 {ALIGNMENTS}，实际 {align}")
    lab = np.arange(1, n, dtype=np.int64)
    obs = lab - 1 if align == "lag1" else lab.copy()
    return obs, lab


def round_boundaries(meta: dict, n: int) -> np.ndarray:
    """得分帧（回合结束）→ 去重排序的帧号数组（排除 0 与越界）。"""
    out: set[int] = set()
    for key in ("round_end_frames_left", "round_end_frames_right"):
        for v in (meta.get(key) or []):
            iv = int(v)
            if 0 < iv < n:
                out.add(iv)
    return np.asarray(sorted(out), dtype=np.int64)


def new_round_start(x: np.ndarray, b: int, jump: float = HP_RESET_JUMP) -> int | None:
    """得分帧 `b` 之后，**新回合第一帧**（血量单帧回升 ≥ jump）；找不到返回 None。

    依据（实测）：第 8246 帧左侧血量 67→0 且右方得分 +1，随后约 750 帧是回放演出
    （双方血量冻结），到第 9000 帧左方血量 0→8800 才是第二回合开始。
    """
    hp = np.stack([x[:, 0], x[:, N_SIDE_COLS]], axis=1)
    for j in range(b + 1, len(x)):
        if hp[j, 0] > 0 and hp[j, 1] > 0 and \
                (hp[j, 0] - hp[j - 1, 0] >= jump or hp[j, 1] - hp[j - 1, 1] >= jump):
            return j
    return None


def play_mask(
    x: np.ndarray, meta: dict, *, rounds: str = "auto", round_margin: int = 0,
) -> tuple[np.ndarray, dict]:
    """返回 (in_play 布尔掩码, 审计信息)。

    rounds:
      "auto"  —— 用 `new_round_start` 定位新回合开始帧，切掉 [得分帧, 新回合开始)；
      "fixed" —— 用 `round_margin` 帧固定窗口（消融用；0 = 不切）；
      "off"   —— 完全不切（消融用，会把演出段当训练数据，**仅用于对照**）。
    """
    n = int(x.shape[0])
    mask = np.ones(n, dtype=bool)
    bounds = round_boundaries(meta, n)
    starts: list[int | None] = []
    if rounds == "off" or (rounds == "fixed" and round_margin <= 0):
        return mask, {"rounds": rounds, "boundaries": bounds.tolist(),
                      "dropped_frames": 0, "new_round_starts": [],
                      "note": "未做回合切段（消融对照）"}
    if rounds == "fixed":
        for b in bounds:
            mask[int(b): min(n, int(b) + int(round_margin))] = False
            starts.append(int(b) + int(round_margin))
    elif rounds == "auto":
        for b in bounds:
            j = new_round_start(x, int(b))
            starts.append(j)
            mask[int(b): (n if j is None else j)] = False
    else:
        raise ValueError(f"rounds 只能是 auto/fixed/off，实际 {rounds}")
    starts_i = [int(s) for s in starts if s is not None]
    return mask, {
        "rounds": rounds, "round_margin": int(round_margin),
        "boundaries": bounds.tolist(), "new_round_starts": starts_i,
        "dropped_frames": int((~mask).sum()), "total_frames": n,
        "note": "切掉的是回放演出/结算段：那里状态被冻结，标签也不再是战斗输入。",
    }


# ---------------------------------------------------------------------------
# 数据集
# ---------------------------------------------------------------------------
@dataclass
class FrameBCData:
    """帧级 BC 数据集（一行 = 一个 (状态, 该侧下一拍输入) 对）。

    `dense` 的前 `base_dim` 列是 `ObservationSpec` 布局（分片能填的 32 维 + 本批无数据的
    128 维零）；其后是"上一拍输入块"（见 `frame_obs.prev_block`），维度由 `prev_mode` 决定。
    """

    dense: np.ndarray            # (M, base_dim + prev_extra_dim) float32
    bullets: np.ndarray          # (M, K, D) float32
    bullet_mask: np.ndarray      # (M, K) float32
    y: np.ndarray                # (M,) int64 联合动作下标（144）
    group: np.ndarray            # (M,) int32 局 ID（= 分片序号）
    tick: np.ndarray             # (M,) int32 局内帧号（= label 帧）
    side: np.ndarray             # (M,) int8  0=左 1=右
    prev_joint: np.ndarray       # (M,) int64 上一拍输入（-100 = 未知），用于持久性基线
    base_dim: int = 0            # dense 中 ObservationSpec 部分的维度
    prev_mode: str = "off"
    shard_names: list[str] = field(default_factory=list)
    align: str = "lag1"
    audit: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.y.shape[0])

    @property
    def n_matches(self) -> int:
        return int(len(np.unique(self.group)))

    def take(self, idx: np.ndarray) -> "FrameBCData":
        return FrameBCData(
            dense=self.dense[idx], bullets=self.bullets[idx], bullet_mask=self.bullet_mask[idx],
            y=self.y[idx], group=self.group[idx], tick=self.tick[idx], side=self.side[idx],
            prev_joint=self.prev_joint[idx], base_dim=self.base_dim, prev_mode=self.prev_mode,
            shard_names=self.shard_names, align=self.align, audit=self.audit)

    def class_counts(self, idx: np.ndarray | None = None) -> np.ndarray:
        y = self.y if idx is None else self.y[idx]
        return np.bincount(y[y >= 0], minlength=ACTION_SPACE_SIZE)

    def persistence_accuracy(self, idx: np.ndarray | None = None) -> float:
        """零参数基线"照抄上一拍"的 top1（上一拍未知的行按多数类兜底，与部署一致）。"""
        y = self.y if idx is None else self.y[idx]
        p = self.prev_joint if idx is None else self.prev_joint[idx]
        prior = np.bincount(y[y >= 0], minlength=ACTION_SPACE_SIZE).argmax()
        pred = np.where(p >= 0, p, prior)
        return float((pred == y).mean())

    def summary(self, idx: np.ndarray | None = None) -> dict:
        y = self.y if idx is None else self.y[idx]
        g = self.group if idx is None else self.group[idx]
        dense = self.dense if idx is None else self.dense[idx]
        base = dense[:, :self.base_dim]
        var = base.var(axis=0) if len(base) else np.zeros(self.base_dim)
        return {
            "rows": int(len(y)), "align": self.align, "prev_mode": self.prev_mode,
            "n_matches": int(len(np.unique(g))),
            "group_counts": {self.shard_names[int(k)] if int(k) < len(self.shard_names)
                             else str(k): int(v)
                             for k, v in zip(*np.unique(g, return_counts=True))},
            "dense_dim": int(dense.shape[1]),
            "base_dim": int(self.base_dim),
            "prev_dim": int(dense.shape[1] - self.base_dim),
            "nonzero_variance_dims": int((var > 1e-12).sum()),
            "persistence_top1": self.persistence_accuracy(idx),
            "side_counts": {"left": int((self.side == 0).sum()),
                            "right": int((self.side == 1).sum())},
            "label": distribution_report(y),
        }


def build_dataset(
    shards: list[FrameShard],
    *,
    spec: ObservationSpec | None = None,
    self_sides: tuple[int, ...] = (0, 1),
    align: str = "lag1",
    score_mode: str = "drop",
    rounds: str = "auto",
    round_margin: int = 0,
    left_is_x: bool = True,
    prev_mode: str = "off",
) -> FrameBCData:
    """把分片列表拼成一个行序为"帧优先、两侧次之"的数据集。

    `prev_mode`：是否把**上一拍输入**作为观测的一块（"off"/"bits"/"joint"，见
    `frame_obs.prev_block` 的长注释 —— 实测它是 0.866 零参数基线的唯一来源）。
    """
    spec = spec or ObservationSpec()
    extra = prev_extra_dim(prev_mode)
    dense_parts: list[np.ndarray] = []
    bul_parts: list[np.ndarray] = []
    bm_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    g_parts: list[np.ndarray] = []
    t_parts: list[np.ndarray] = []
    s_parts: list[np.ndarray] = []
    p_parts: list[np.ndarray] = []
    names: list[str] = []
    audits: list[dict] = []

    for gi, sh in enumerate(shards):
        n = sh.frames
        mask, seg = play_mask(sh.x, sh.meta, rounds=rounds, round_margin=round_margin)
        char_x = float(sh.meta.get("char_x", 0) or 0)
        char_y = float(sh.meta.get("char_y", 0) or 0)
        per_side: dict[int, tuple] = {}
        for s in self_sides:
            labels = joint_labels(sh.inp[:, s])
            obs_i, lab_i = alignment_pairs(n, align)
            keep = (labels[lab_i] >= 0) & mask[lab_i]
            obs_i, lab_i = obs_i[keep], lab_i[keep]
            lab_vals = labels[lab_i]
            ch_self = char_x if (s == 0) == bool(left_is_x) else char_y
            ch_opp = char_y if (s == 0) == bool(left_is_x) else char_x
            vec = vectorize_frames(
                sh.x, sh.hand, self_side=s, spec=spec,
                bullets=sh.bullet, bullet_mask=sh.bullet_mask,
                char_self=ch_self, char_opp=ch_opp, score_mode=score_mode)
            # 上一拍输入：按 **label 帧** 索引（不是观测帧）—— 它是"此刻已按住的键"，
            # 与观测帧无关；lag0/lag1 下都取 label 帧的前一帧。
            # 用**前向填充**而不是直接取 inp[k-1]：喂入闸门（--feed-gate）在回合演出段
            # 不推进输入指针、改为"保持上一次输入"，因此那几帧的 -1 占位并不代表"没按"，
            # 真正在生效的仍是最后一次真输入。填充后 prev 的语义才与游戏一致。
            prev_raw = _prev_inputs(sh.inp[:, s].astype(np.int64), lab_i)
            per_side[s] = (vec, obs_i, lab_i, lab_vals, prev_raw)
        # 行序：先按 label 帧号，再按侧 → block 切分的验证集同时含左右两侧
        lab_all = np.concatenate([per_side[s][2] for s in self_sides])
        side_all = np.concatenate([np.full(per_side[s][2].shape, s, dtype=np.int8)
                                   for s in self_sides])
        order = np.lexsort((side_all, lab_all))
        lab_all, side_all = lab_all[order], side_all[order]

        d = np.zeros((lab_all.size, spec.dense_dim + extra), dtype=np.float32)
        y = np.zeros(lab_all.size, dtype=np.int64)
        pj = np.full(lab_all.size, IGNORE_INDEX, dtype=np.int64)
        bul = np.zeros((lab_all.size, spec.n_bullets, spec.bullet_dim), dtype=np.float32)
        bm = np.zeros((lab_all.size, spec.n_bullets), dtype=np.float32)
        for s in self_sides:
            vec, obs_i, lab_i, lab_vals, prev_raw = per_side[s]
            sel = side_all == s
            # side_all[sel] 中同一侧内部仍按帧升序（lexsort 主键是帧号）
            order_s = lab_all[sel].argsort(kind="stable")
            obs_sel = obs_i[order_s]
            d[sel, :spec.dense_dim] = vec.dense[obs_sel]
            if extra:
                d[sel, spec.dense_dim:] = prev_block(prev_raw[order_s], prev_mode)
            pj[sel] = joint_labels(prev_raw)[order_s]
            bul[sel] = vec.bullets[obs_sel]
            bm[sel] = vec.bullet_mask[obs_sel]
            y[sel] = lab_vals[order_s]
        dense_parts.append(d)
        bul_parts.append(bul)
        bm_parts.append(bm)
        y_parts.append(y)
        p_parts.append(pj)
        g_parts.append(np.full(len(y), gi, dtype=np.int32))
        t_parts.append(lab_all.astype(np.int32))
        s_parts.append(side_all)
        names.append(sh.match_id)
        audits.append({
            "shard": sh.name, "file": sh.meta.get("file"),
            "frames": n, "rows": int(len(y)), "play_mask": seg,
            "labels_left": label_report(sh.inp[:, 0]) if 0 in self_sides else None,
            "labels_right": label_report(sh.inp[:, 1]) if 1 in self_sides else None,
        })

    n_rows = sum(int(p.shape[0]) for p in y_parts)
    dense = np.concatenate(dense_parts) if dense_parts \
        else np.zeros((0, spec.dense_dim + extra), np.float32)
    if dense.size and not np.isfinite(dense).all():
        raise ValueError("观测 dense 含 NaN/Inf；禁止把脏数据喂进训练（检查分片原始列）")
    if dense.size and (dense.min() < -1e-6 or dense.max() > 1 + 1e-6):
        raise ValueError(f"观测 dense 越界 [{dense.min():.3f},{dense.max():.3f}]，应在 [0,1]")
    return FrameBCData(
        dense=dense,
        prev_joint=np.concatenate(p_parts) if p_parts
        else np.full(0, IGNORE_INDEX, np.int64),
        base_dim=int(spec.dense_dim), prev_mode=prev_mode,
        bullets=np.concatenate(bul_parts) if bul_parts
        else np.zeros((0, spec.n_bullets, spec.bullet_dim), np.float32),
        bullet_mask=np.concatenate(bm_parts) if bm_parts
        else np.zeros((0, spec.n_bullets), np.float32),
        y=np.concatenate(y_parts) if y_parts else np.zeros(0, np.int64),
        group=np.concatenate(g_parts) if g_parts else np.zeros(0, np.int32),
        tick=np.concatenate(t_parts) if t_parts else np.zeros(0, np.int32),
        side=np.concatenate(s_parts) if s_parts else np.zeros(0, np.int8),
        shard_names=names, align=align,
        audit={"shards": audits, "score_mode": score_mode,
               "rounds": rounds, "round_margin": round_margin, "rows": n_rows},
    )


def make_split(
    data: FrameBCData, *, mode: str = "block", val_frac: float = 0.2, seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """(train_idx, val_idx)。

    mode="group" 需要 ≥2 个分片（局级留出，无邻域泄漏）；只有 1 个分片时**报错**，
    因为"用同一局的后半段当验证集"虽然可用，但必须由调用方显式选 block，
    不能在这里静默降级（沿用 dataset.split_indices 的立场）。
    """
    n = len(data)
    if mode == "group":
        if data.n_matches < 2:
            raise ValueError(
                f"只有 {data.n_matches} 个分片，无法做局级切分。"
                "请用 --split block（时间尾巴留出），或先跑 tools/rep_drive.py --bulk 扩充分片。")
        return split_indices(n, "group", val_frac=val_frac, seed=seed, group=data.group)
    return split_indices(n, mode, val_frac=val_frac, seed=seed)


__all__ = [
    "IGNORE_INDEX", "ALIGNMENTS", "HP_RESET_JUMP", "DIR_NAMES", "BTN_NAMES",
    "FrameShard", "load_shard", "discover_shards", "joint_labels", "label_report",
    "action_name", "distribution_report", "alignment_pairs", "round_boundaries",
    "new_round_start", "play_mask", "FrameBCData", "build_dataset", "make_split",
]
