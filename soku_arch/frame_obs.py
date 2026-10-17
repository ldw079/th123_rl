# -*- coding: utf-8 -*-
"""帧级分片 → 观测 v2 向量：**只搬运真实存在的信息，缺口逐个显式登记**。

背景（docs/STATUS.md §2）：帧级 BC 的观测 = 分片 `x` 的 20 列 + `hand`。
但 `observation.ObservationSpec` 有 160 维，分片只覆盖其中一部分
（例如 `facing`/`vel_*`/`skills`/`weather`/`guard_frames` 都不在分片里）。

本模块刻意不做两件事：
  1. **不猜**：不存在的字段一律写 0，并在 `AVAILABILITY` 里点名；
     `ObservationSpec.coverage_report` 会把它们报成"零方差维 = 本批数据里没信息"。
  2. **不把分数当连续特征喂**（STATUS 陷阱 3）：`score` 是**回合胜场**（0/1/2 的计数），
     默认 `score_mode="drop"` 把它与由它派生的 `round_index` 一起清零；
     需要时用 `score_mode="raw"` 打开做消融，绝不默认静默喂进去。

坐标量纲：分片 `x` 是**舞台绝对横坐标**（实测 40..1240），与
`observation.STAGE_WIDTH = 1240` 同量纲；而 `Field("pos_x", lo=STAGE_X_MIN, hi=STAGE_X_MAX)`
是更宽的归一化区间 —— 两者语义分别是"绝对位置"与"相对墙距"，都保留。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .observation import (
    CARD_FIELDS,
    CONTEXT_FIELDS,
    PLAYER_FIELDS,
    RELATIVE_FIELDS,
    STAGE_WIDTH,
    ObservationSpec,
)
from .input_codec import BattleInput

# 分片 `x` 的每侧 10 列（顺序即 tools/rep_drive.SIDE_COLS）
SIDE_COLS: tuple[str, ...] = (
    "hp", "spirit", "x", "y", "action", "pose", "airBorne", "cardGauge", "hand_n",
    "score",
)
N_SIDE_COLS = len(SIDE_COLS)
HAND_SLOTS = 5
EMPTY_HAND = 255          # 0xFF 哨兵（实测：空手牌）
CARD_ID_MAX = 255.0       # hand_id_* 的 Field 上界

PF = {f.name: f for f in PLAYER_FIELDS}
CF = {f.name: f for f in CARD_FIELDS}
RF = {f.name: f for f in RELATIVE_FIELDS}
CTXF = {f.name: f for f in CONTEXT_FIELDS}

# ---------------------------------------------------------------------------
# 可用性台账：dense 里的字段名 → 来源说明。
# 这张表是"诚实清单"：`written_slots()` 由它推导，单测断言未登记字段恒为 0。
# ---------------------------------------------------------------------------
AVAILABILITY: dict[str, str] = {
    "self_hp": "分片列 hp",
    "self_spirit": "分片列 spirit",
    "self_pos_x": "分片列 x",
    "self_pos_y": "分片列 y",
    "self_air_borne": "分片列 airBorne",
    "self_action": "分片列 action",
    "self_pose": "分片列 pose",
    "self_card_gauge": "分片列 cardGauge",
    "opp_hp": "分片列 hp（对手侧）",
    "opp_spirit": "分片列 spirit",
    "opp_pos_x": "分片列 x",
    "opp_pos_y": "分片列 y",
    "opp_air_borne": "分片列 airBorne",
    "opp_action": "分片列 action",
    "opp_pose": "分片列 pose",
    "opp_card_gauge": "分片列 cardGauge",
    "hand_count": "分片列 hand_n（self 一侧）",
    "hand_id_0": "分片 hand[self,0]（255=空 → 1.0）",
    "hand_id_1": "分片 hand[self,1]",
    "hand_id_2": "分片 hand[self,2]",
    "hand_id_3": "分片 hand[self,3]",
    "hand_id_4": "分片 hand[self,4]",
    "dx": "派生：opp.x - self.x",
    "dy": "派生：opp.y - self.y",
    "adx_abs": "派生：|dx|",
    "dist_left_corner": "派生：self.x",
    "dist_right_corner": "派生：STAGE_WIDTH - self.x",
    "is_cornered": "派生：min(self.x, W-self.x) < 120",
    "opp_cornered": "派生：对手同上",
    "wall_dist": "派生：min(self.x, W-self.x)/2",
    "self_char_norm": "分片 meta.char_x/char_y（按 left_is_x 归属）",
    "opp_char_norm": "分片 meta.char_x/char_y（按 left_is_x 归属）",
    # 仅 score_mode="raw" 时才写；默认丢弃
    "self_score": "分片列 score（**默认丢弃**，见 score_mode）",
    "opp_score": "分片列 score（**默认丢弃**）",
    "round_index": "派生：self.score + opp.score（**默认丢弃**）",
}

MISSING_FIELDS: tuple[str, ...] = (
    "self_/opp_ vel_x, vel_y（包内无自身速度；逐帧差分是另一回事）",
    "self_/opp_ facing（分片无朝向 → facing_dx / dist_front_corner / dist_back_corner 无法派生）",
    "self_/opp_ max_spirit, pose_frame, frame_count, sequence, hit_stop, time_stop,"
    " untech, air_dash_count, super_armor_hp, combo_damage, combo_limit,"
    " guard_frames, invuln_frames, drop_invul_left, healing_charm, confusion,"
    " sword_of_rapture, image, turn_recency, object_count",
    "hand_cost_0..4, selected_slot, hand_masked_by_weather, affordable_count",
    "skill_level_0..14, fan/rods/books/doll/drop_level",
    "weather_active_*, weather_displayed_*, weather_timer, weather_effect_hidden",
    "match_timer",
    "bullets(16×9)（mod 有 objects，但 rep_drive 未落盘 → mask 全 0）",
)

# 附在 spec 之后的"动作上下文"块（见 prev_block 的长注释）
PREV_BLOCK_NOTE = (
    "上一拍输入块（prev_block）：第 0 维=有效位，其后为 12 位原始 BattleKeys（bits）"
    "或 144 one-hot（joint）。**实测它有决定性作用**：照抄上一拍这条零参数基线 "
    "top1=0.8751（验证集），而不含它的观测器只有 0.33–0.34（且越训越差）。"
)


def availability_report() -> dict:
    return {
        "available": AVAILABILITY,
        "missing": list(MISSING_FIELDS),
        "prev_block": PREV_BLOCK_NOTE,
        "note": "missing 里的字段在本批分片中**没有数据**，dense 里恒为 0；"
                "coverage_report 的零方差维就是它们的显式证据。"
                "补齐方式：扩展 tools/rep_drive.py 的分片写入（objects/weather 已在包内可得）。",
    }


def written_slots(spec: ObservationSpec | None = None,
                  score_mode: str = "drop") -> set[int]:
    """`vectorize_frames` 实际会写入的 dense 下标集合（单一事实来源）。"""
    spec = spec or ObservationSpec()
    off = spec.field_offsets
    names = [n for n in AVAILABILITY]
    if score_mode == "drop":
        names = [n for n in names if n not in ("self_score", "opp_score", "round_index")]
    return {off[n] for n in names}


def _norm(field, values: np.ndarray) -> np.ndarray:
    """按 Field 的 [lo,hi] 线性归一化到 [0,1]；NaN/inf → 0。"""
    v = np.asarray(values, dtype=np.float64)
    span = float(field.hi) - float(field.lo)
    if span == 0:
        return np.zeros_like(v, dtype=np.float32)
    out = (v - float(field.lo)) / span
    out = np.where(np.isfinite(out), out, 0.0)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


@dataclass(frozen=True)
class FrameVector:
    """一局分片向量化后的观测张量（以某一侧为 self 构造）。"""

    dense: np.ndarray        # (N, dense_dim) float32
    bullets: np.ndarray      # (N, K, D) float32
    bullet_mask: np.ndarray  # (N, K) float32
    side: int                # 0=左 / 1=右（这一侧是 self）
    spec: ObservationSpec


# ---------------------------------------------------------------------------
# 上一拍输入块（"动作上下文"）
#
# 为什么必须有它（**实测**，不是设计偏好）：
#   非想天则里按键会被按住几十帧，于是 `inp[i]` 的最大预测源是 `inp[i-1]` 本身。
#   实测"照抄上一拍"这一条零参数基线在本批分片上 top1 = **0.8751**（验证集）；
#   而不含该信息的逐帧观测器（MLP/软前缀 LLM）只有 0.33–0.34，且**越训越差**
#   （类权重把概率推向稀有类，而它根本没有"现在按着什么"可用）。也就是说：
#   **缺的不是容量，是"现在按着什么"这个输入**。
#   在线环路里它天然可得（就是自己上一拍的输出），因此把它作为观测的一块显式登记。
#
# 代价必须写清：训练期喂的是**专家的**上一拍输入，部署期喂的是**自己的**上一拍输出
#   → 标准 BC 的 exposure bias，报告里逐臂给出，不做掩盖。
# ---------------------------------------------------------------------------
PREV_MODES: tuple[str, ...] = ("off", "bits", "joint")
PREV_RAW_BITS = 12            # BattleKeys 全 12 位（含 AandB/BandC/pause/select，无损）
PREV_JOINT_DIM = 144          # 144 联合动作 one-hot
PREV_VALID_DIM = 1            # 1 维有效位：上一拍输入未知（首帧/回合重置）时为 0


def prev_extra_dim(mode: str = "off") -> int:
    """附加块维度（含 1 维有效位）。"""
    if mode == "off":
        return 0
    if mode == "bits":
        return PREV_RAW_BITS + PREV_VALID_DIM
    if mode == "joint":
        return PREV_JOINT_DIM + PREV_VALID_DIM
    raise ValueError(f"prev_mode 只能是 {PREV_MODES}，实际 {mode}")


def prev_block(raw_prev: np.ndarray, mode: str = "off") -> np.ndarray:
    """上一拍原始 u16（-1 = 未知）→ (n, prev_extra_dim)。

    第 0 列是有效位；`mode="joint"` 时用 144 联合动作 one-hot（与动作空间同构，
    使"照抄上一拍"在观测里就是一次恒等映射，便于诊断模型是否学到了这一步）。
    """
    raw = np.asarray(raw_prev).reshape(-1)
    n = raw.shape[0]
    if mode == "off":
        return np.zeros((n, 0), dtype=np.float32)
    out = np.zeros((n, prev_extra_dim(mode)), dtype=np.float32)
    valid = raw >= 0
    out[valid, 0] = 1.0
    if mode == "bits":
        for b in range(PREV_RAW_BITS):
            out[valid, 1 + b] = ((raw[valid] >> b) & 1).astype(np.float32)
    else:
        for i in np.flatnonzero(valid):
            out[i, 1 + BattleInput(int(raw[i])).joint_index] = 1.0
    return out



def vectorize_frames(
    x: np.ndarray,
    hand: np.ndarray,
    *,
    self_side: int,
    spec: ObservationSpec | None = None,
    bullets: np.ndarray | None = None,
    bullet_mask: np.ndarray | None = None,
    char_self: float = 0.0,
    char_opp: float = 0.0,
    score_mode: str = "drop",
) -> FrameVector:
    """分片数组 → (dense, bullets, bullet_mask)。

    参数
      x          : (N, 20) 两侧拼接的 10 列（列序见 SIDE_COLS）
      hand       : (N, 2, 5) 卡 ID（255=空）
      self_side  : 0 表示把左当成 self（对手=右），1 反之
      score_mode : "drop"（默认，遵守 STATUS 陷阱 3）/ "raw"

    对手手牌是隐藏信息，**不进观测**（只有 self 的 5 张 + hand_n）。
    """
    spec = spec or ObservationSpec()
    x = np.asarray(x, dtype=np.float64)
    hand = np.asarray(hand)
    if x.ndim != 2 or x.shape[1] != 2 * N_SIDE_COLS:
        raise ValueError(f"x 形状应为 (N,{2 * N_SIDE_COLS})，实际 {x.shape}")
    if hand.shape != (x.shape[0], 2, HAND_SLOTS):
        raise ValueError(f"hand 形状应为 (N,2,{HAND_SLOTS})，实际 {hand.shape}")
    if self_side not in (0, 1):
        raise ValueError(f"self_side 只能是 0/1，实际 {self_side}")
    if score_mode not in ("drop", "raw"):
        raise ValueError(f"score_mode 只能是 drop/raw，实际 {score_mode}")

    n = x.shape[0]
    sb, ob = self_side * N_SIDE_COLS, (1 - self_side) * N_SIDE_COLS
    idx = {c: i for i, c in enumerate(SIDE_COLS)}
    S = {c: x[:, sb + i] for c, i in idx.items()}
    O = {c: x[:, ob + i] for c, i in idx.items()}

    off = spec.field_offsets
    dense = np.zeros((n, spec.dense_dim), dtype=np.float32)

    for tag, P in (("self", S), ("opp", O)):
        dense[:, off[f"{tag}_hp"]] = _norm(PF["hp"], P["hp"])
        dense[:, off[f"{tag}_spirit"]] = _norm(PF["spirit"], P["spirit"])
        dense[:, off[f"{tag}_pos_x"]] = _norm(PF["pos_x"], P["x"])
        dense[:, off[f"{tag}_pos_y"]] = _norm(PF["pos_y"], P["y"])
        dense[:, off[f"{tag}_air_borne"]] = _norm(PF["air_borne"], P["airBorne"])
        dense[:, off[f"{tag}_action"]] = _norm(PF["action"], P["action"])
        dense[:, off[f"{tag}_pose"]] = _norm(PF["pose"], P["pose"])
        dense[:, off[f"{tag}_card_gauge"]] = _norm(PF["card_gauge"], P["cardGauge"])
        if score_mode == "raw":
            dense[:, off[f"{tag}_score"]] = _norm(PF["score"], P["score"])

    # ---- 手牌（仅 self 一侧）----
    dense[:, off["hand_count"]] = _norm(CF["hand_count"], S["hand_n"])
    for i in range(HAND_SLOTS):
        dense[:, off[f"hand_id_{i}"]] = np.clip(
            hand[:, self_side, i] / CARD_ID_MAX, 0.0, 1.0).astype(np.float32)

    # ---- 相对量（所有可派生项）----
    dx = O["x"] - S["x"]
    dy = O["y"] - S["y"]
    dense[:, off["dx"]] = _norm(RF["dx"], dx)
    dense[:, off["dy"]] = _norm(RF["dy"], dy)
    dense[:, off["adx_abs"]] = _norm(RF["adx_abs"], np.abs(dx))
    dense[:, off["dist_left_corner"]] = _norm(RF["dist_left_corner"], S["x"])
    dense[:, off["dist_right_corner"]] = _norm(
        RF["dist_right_corner"], STAGE_WIDTH - S["x"])
    dense[:, off["is_cornered"]] = _norm(
        RF["is_cornered"], (np.minimum(S["x"], STAGE_WIDTH - S["x"]) < 120).astype(float))
    dense[:, off["opp_cornered"]] = _norm(
        RF["opp_cornered"], (np.minimum(O["x"], STAGE_WIDTH - O["x"]) < 120).astype(float))
    dense[:, off["wall_dist"]] = _norm(
        RF["wall_dist"], np.minimum(S["x"], STAGE_WIDTH - S["x"]) / 2.0)
    # facing_dx / dist_front_corner / dist_back_corner：分片无朝向 → **无法派生**，保持 0

    # ---- 上下文 ----
    if score_mode == "raw":
        dense[:, off["round_index"]] = _norm(CTXF["round_index"], S["score"] + O["score"])
    dense[:, off["self_char_norm"]] = _norm(
        CTXF["self_char_norm"], np.full(n, float(char_self)))
    dense[:, off["opp_char_norm"]] = _norm(
        CTXF["opp_char_norm"], np.full(n, float(char_opp)))

    if bullets is None:
        bul = np.zeros((n, spec.n_bullets, spec.bullet_dim), dtype=np.float32)
        bm = np.zeros((n, spec.n_bullets), dtype=np.float32)
    else:
        bul = np.asarray(bullets, dtype=np.float32)
        bm = (np.asarray(bullet_mask, dtype=np.float32) if bullet_mask is not None
              else np.ones(bul.shape[:2], dtype=np.float32))
        if bul.shape[0] != n:
            raise ValueError(f"bullets 行数 {bul.shape[0]} 与 x 行数 {n} 不一致")

    return FrameVector(dense=dense, bullets=bul, bullet_mask=bm, side=self_side, spec=spec)


__all__ = [
    "SIDE_COLS", "N_SIDE_COLS", "HAND_SLOTS", "EMPTY_HAND", "CARD_ID_MAX",
    "AVAILABILITY", "MISSING_FIELDS", "PREV_BLOCK_NOTE",
    "availability_report", "written_slots",
    "PREV_MODES", "PREV_RAW_BITS", "PREV_JOINT_DIM", "PREV_VALID_DIM",
    "prev_extra_dim", "prev_block",
    "FrameVector", "vectorize_frames",
]
