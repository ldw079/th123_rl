# -*- coding: utf-8 -*-
"""观测 v2：**全面**状态规格（声明式，可向量化、可合成、可校验）。

为什么要有这一层（本次授权的直接落实）：
  旧 11 维观测缺自身动作/姿态、自身 airBorne、卡片槽、手牌、四角距离、弹幕 objects；
  旧 260 维（feat_builder）补了这些，但**自己也有空槽**：own_vx/own_vy、turn_recency、
  guard_frames、evasion_count、opp_char_onehot 一律填 0，属性 proxy 硬编码 0.5。
  因此本规格的目标不是"复制 260"，而是**声明式地把该有的信息全部登记**，
  并逐个标注来源与是否已证实（verify 标记），让缺口显式可见。

设计原则
  1. 每个字段都带 `source`（SokuLib/Env.py 的原始字段名，或 "需 mod 补"）与 `verify` 标记。
  2. 分组：self / opp / relative / cards / skills / weather / context / bullets。
  3. 弹幕用**变长集合**表示（K 个对象 × 每对象若干量），由 `obs_encoder.BulletSetEncoder`
     做置换不变池化 —— 取代旧版 6×6 网格量化（网格丢失了"哪颗弹在哪个方向多快"）。
  4. 本规格只负责"信息如何摆平成向量"，**不负责 token 数**：
     `obs_encoder.ObservationEncoder` 把它压成 K 个软前缀 token，
     因此输入维度可以很大而序列长度不变（这是本次架构的关键取舍）。

来源标注
  [E] D:\\temp\\build\\SokuAI-master\\Training\\AITrainerScriptPYTorch\\Soku\\Env.py 的完整 spec
  [F] C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\feat_builder.py（260 维核心侧特征）
  [S] D:\\temp\\build\\SokuAI-master\\SokuLib\\src\\*.hpp
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .constants import N_WEATHER

# 位置/量纲常量（来源 [F] feat_builder.py 与 [E] Env.py 的 Bounded 范围）
STAGE_X_MIN, STAGE_X_MAX = -900.0, 2200.0
STAGE_Y_MIN, STAGE_Y_MAX = -100.0, 2200.0
STAGE_WIDTH = 1240.0          # feat_builder.py:337 用 1240- x 作墙距
HP_MAX = 10000.0              # Env.py: Bounded(0, 10000)
SPIRIT_MAX = 2000.0           # feat_builder.py:182 除以 2000
CARD_GAUGE_MAX = 900.0        # Env.py: Bounded(0, 900)
ACTION_MAX = 799.0            # Env.py: Bounded(0, 799)
N_ACTION_CLASS = 8            # feat_builder.py:197 action//128 分 8 类
N_BULLETS = 16                # 每对象字段见 BULLET_FIELDS
# 依据 packet.hpp:102-108 的 Object 结构（direction / relativePosMe / relativePosOpponent /
# action / imageID）扩展。**注意：包里没有速度**，rel_vx/rel_vy 是客户端逐帧差分派生的
# （旧实现见 feat_builder.py:77-104 按 seq 匹配差分）—— 新弹速度=0、丢帧时速度错误，
# 因此这两个字段必须按"派生、可信度较低"对待。
BULLET_FIELDS: tuple[str, ...] = (
    "rel_x", "rel_y",              # relativePosMe
    "rel_x_opp", "rel_y_opp",      # relativePosOpponent（包里有，旧实现未用）
    "direction", "action_norm", "image_norm",
    "rel_vx", "rel_vy",            # 派生（差分），非传输字段
)


@dataclass
class Field:
    """字段声明。

    **参数顺序刻意设计为 (name, group, lo, hi, source, ...)** —— 因为绝大多数调用
    都按这个自然顺序写。dim 放在 lo/hi 之后，避免"把 HP_MAX 传成 dim"这类静默错误
    （初版就踩了这个坑：dim 在前时 Field("hp","player",0,HP_MAX,"src") 会把 dim 设为 0）。
    """

    name: str
    group: str
    lo: float = 0.0
    hi: float = 1.0
    source: str = ""
    dim: int = 1
    verify: bool = False       # True = 目前拿不到/未证实，必须显式暴露
    note: str = ""

    def normalize(self, v: float) -> float:
        if not np.isfinite(v):
            return 0.0
        span = self.hi - self.lo
        return float(np.clip((v - self.lo) / span, 0.0, 1.0)) if span else 0.0


# --------------------------------------------------------------------------
# 单侧玩家字段（self 与 opp 共用同一布局；两侧都从包内可得）
# --------------------------------------------------------------------------
PLAYER_FIELDS: tuple[Field, ...] = (
    Field("hp", "player", 0, HP_MAX, "[E] left['hp']"),
    Field("spirit", "player", 0, SPIRIT_MAX, "[F]:182 left['spirit']/2000", verify=True,
          note="suika 档实测最大 65.49，量纲待裁定（见 VERIFY V3）"),
    Field("max_spirit", "player", 0, SPIRIT_MAX, "[E] maxSpirit"),
    Field("pos_x", "player", STAGE_X_MIN, STAGE_X_MAX, "[E] position.x"),
    Field("pos_y", "player", STAGE_Y_MIN, STAGE_Y_MAX, "[E] position.y"),
    Field("vel_x", "player", -30, 30, "**需 mod 补**：包内无自身 vx", verify=True,
          note="旧 260 维把它填 0（feat_builder.py:231/234），必须补"),
    Field("vel_y", "player", -30, 30, "**需 mod 补**：包内无自身 vy", verify=True),
    Field("facing", "player", -1, 1, "[E] direction"),
    Field("air_borne", "player", 0, 1, "[E] airBorne"),
    Field("action", "player", 0, ACTION_MAX, "[E] action"),
    Field("pose", "player", 0, 2000, "[E] pose"),
    Field("pose_frame", "player", 0, 600, "[E] poseFrame"),
    Field("frame_count", "player", 0, 600, "[E] frameCount"),
    Field("sequence", "player", 0, 999, "[E] sequence"),
    Field("hit_stop", "player", 0, 120, "[E] hitStop"),
    Field("time_stop", "player", 0, 120, "[E] timeStop"),
    Field("untech", "player", 0, 900, "[E] untech"),
    Field("air_dash_count", "player", 0, 3, "[E] airDashCount"),
    Field("super_armor_hp", "player", -HP_MAX, HP_MAX, "[E] superArmorHp"),
    Field("combo_damage", "player", 0, 3000, "[E] comboDamage"),
    Field("combo_limit", "player", 0, 3000, "[E] comboLimit"),
    Field("guard_frames", "player", 0, 600, "**需 mod 补**：旧 260 维填 0（:343）", verify=True),
    Field("invuln_frames", "player", 0, 600, "**需 mod 补**", verify=True),
    Field("drop_invul_left", "player", 0, 1200, "[E] dropInvulTimeLeft"),
    Field("healing_charm", "player", 0, 250, "[E] healingCharm"),
    Field("confusion", "player", 0, 900, "[E] confusion"),
    Field("sword_of_rapture", "player", 0, 900, "[E] swordOfRapture"),
    Field("card_gauge", "player", 0, CARD_GAUGE_MAX, "[E] cardGauge（晴岚哨兵 0xFFFF 需归一为 0）"),
    Field("score", "player", 0, 2, "[E] score"),
    Field("image", "player", 0, 2000, "[E] image（动画图号）"),
    Field("turn_recency", "player", 0, 600, "**需 mod 补**：旧 260 维填 0（:201）", verify=True),
    Field("object_count", "player", 0, 48, "[CS] soku_client2.py:53 objectCount —— 已在传，旧观测未用"),
)

# 角色等级（已传输但旧观测未用：[CS] soku_client2.py:50）
CHAR_LEVEL_FIELDS: tuple[Field, ...] = (
    Field("fan_level", "char_levels", 0, 4, "[CS] fanLevel（早苗/灵梦等扇系）"),
    Field("rods_level", "char_levels", 0, 4, "[CS] rodsLevel"),
    Field("books_level", "char_levels", 0, 4, "[CS] booksLevel"),
    Field("doll_level", "char_levels", 0, 4, "[CS] dollLevel"),
    Field("drop_level", "char_levels", 0, 3, "[CS] dropLevel"),
)

RELATIVE_FIELDS: tuple[Field, ...] = (
    Field("dx", "relative", -(STAGE_X_MAX - STAGE_X_MIN), STAGE_X_MAX - STAGE_X_MIN, "派生：right.x-left.x"),
    Field("dy", "relative", -(STAGE_Y_MAX - STAGE_Y_MIN), STAGE_Y_MAX - STAGE_Y_MIN, "派生"),
    Field("adx_abs", "relative", 0, STAGE_WIDTH, "派生 |dx|"),
    Field("facing_dx", "relative", -(STAGE_WIDTH), STAGE_WIDTH, "派生：按自身朝向镜像后的 dx（去掉左右对称冗余）"),
    Field("dist_left_corner", "relative", 0, STAGE_WIDTH, "**派生**：position.x（部署包无 distTo*Corner）"),
    Field("dist_right_corner", "relative", 0, STAGE_WIDTH, "**派生**：STAGE_WIDTH - position.x"),
    Field("dist_front_corner", "relative", 0, STAGE_WIDTH, "**派生**：按朝向取前后"),
    Field("dist_back_corner", "relative", 0, STAGE_WIDTH, "**派生**：按朝向取前后"),
    Field("is_cornered", "relative", 0, 1, "派生：自身距任一侧墙 <120"),
    Field("opp_cornered", "relative", 0, 1, "派生：对手距任一侧墙 <120"),
    Field("wall_dist", "relative", 0, STAGE_WIDTH / 2, "[F]:337 舞台控制势用"),
)

CARD_FIELDS: tuple[Field, ...] = (
    Field("hand_count", "cards", 0, 5, "[F]:292"),
    Field("hand_id_0", "cards", 0, 255, "[E] hand[0].id（0xFF=空）"),
    Field("hand_id_1", "cards", 0, 255, "[E] hand[1].id"),
    Field("hand_id_2", "cards", 0, 255, "[E] hand[2].id"),
    Field("hand_id_3", "cards", 0, 255, "[E] hand[3].id"),
    Field("hand_id_4", "cards", 0, 255, "[E] hand[4].id"),
    Field("hand_cost_0", "cards", 0, 5, "[E] hand[0].cost"),
    Field("hand_cost_1", "cards", 0, 5, "[E] hand[1].cost"),
    Field("hand_cost_2", "cards", 0, 5, "[E] hand[2].cost"),
    Field("hand_cost_3", "cards", 0, 5, "[E] hand[3].cost"),
    Field("hand_cost_4", "cards", 0, 5, "[E] hand[4].cost"),
    Field("selected_slot", "cards", 0, 5, "派生：当前选中卡槽位"),
    Field("hand_masked_by_weather", "cards", 0, 1, "晴岚遮蔽标志（信息对称例外之一）"),
    Field("affordable_count", "cards", 0, 5, "派生：gauge 足够支付的卡数（旧 260 维只给二值，:310）"),
)

SKILL_FIELDS: tuple[Field, ...] = tuple(
    Field(f"skill_level_{i}", "skills", 0, 4, "[E] skills[i]") for i in range(15)
)

WEATHER_FIELDS: tuple[Field, ...] = (
    *tuple(Field(f"weather_active_{i}", "weather", 0, 1, "[E] weather.active") for i in range(N_WEATHER)),
    *tuple(Field(f"weather_displayed_{i}", "weather", 0, 1, "[E] weather.displayed") for i in range(N_WEATHER)),
    Field("weather_timer", "weather", 0, 999, "[E] weather.timer"),
    Field("weather_effect_hidden", "weather", 0, 1, "极光：实际效果隐藏（信息对称例外之二）"),
    Field("weather_mismatch", "weather", 0, 1, "派生：active != displayed"),
)

CONTEXT_FIELDS: tuple[Field, ...] = (
    Field("round_index", "context", 0, 2, "派生：当前第几回合"),
    Field("match_timer", "context", 0, 99, "**需 mod 补**：回合剩余时间", verify=True),
    Field("self_char_norm", "context", 0, 36, "[S] Character.hpp 0..36"),
    Field("opp_char_norm", "context", 0, 36, "[S] Character.hpp 0..36（旧 260 维填 0，:322）"),
)

ALL_DENSE_FIELDS: tuple[Field, ...] = (
    tuple(replace(f, name=f"self_{f.name}") for f in PLAYER_FIELDS)
    + tuple(replace(f, name=f"opp_{f.name}") for f in PLAYER_FIELDS)
    + RELATIVE_FIELDS + CARD_FIELDS + SKILL_FIELDS + CHAR_LEVEL_FIELDS
    + WEATHER_FIELDS + CONTEXT_FIELDS
)


LEGACY_COMPAT_FIELDS: tuple[Field, ...] = tuple(
    Field(f"legacy_{n}", "legacy_compat", 0.0, 1.0,
          "旧 11 维兼容块（迁移期 A/B 专用，采集到 X_v2 后删除）")
    for n in ("adx", "spirit", "close", "prev_macro", "game_frame", "dy",
              "opp_air", "bullet_near", "i_am_left", "tti", "opp_corner")
)


@dataclass
class ObservationSpec:
    """全面观测规格：声明 + 向量化 + 合成。

    include_legacy_compat：追加 11 维"旧观测兼容块"。
    存在理由（**仅供迁移期 A/B，采集到 X_v2 后必须删除**）：
      旧 11 维里有 5 个特征（close / bullet_near / i_am_left / tti / prev_macro）
      在 v2 布局中没有对应字段，若不兼容就**无法在真实旧数据上做公平的新旧对照**
      （会让 v2 侧平白少 5 个特征，得出的差异是"缺特征"而不是"架构差异"）。
      兼容块让两侧看到**完全相同的 11 维信息**，唯一变量只剩读数路径。
      兼容块内的数值期望**已由调用方归一化到 [0,1]**（见 data_v2.from_legacy_11）。
    """

    n_bullets: int = N_BULLETS
    fields: tuple[Field, ...] = ALL_DENSE_FIELDS
    groups: tuple[str, ...] = ("self", "opp", "relative", "cards", "skills", "weather", "context")
    include_legacy_compat: bool = False
    n_features_compat: int = len(LEGACY_COMPAT_FIELDS)

    @property
    def player_dim(self) -> int:
        return sum(f.dim for f in PLAYER_FIELDS)

    @property
    def relative_dim(self) -> int:
        return sum(f.dim for f in RELATIVE_FIELDS)

    @property
    def card_dim(self) -> int:
        return sum(f.dim for f in CARD_FIELDS)

    @property
    def skill_dim(self) -> int:
        return sum(f.dim for f in SKILL_FIELDS)

    @property
    def weather_dim(self) -> int:
        return sum(f.dim for f in WEATHER_FIELDS)

    @property
    def context_dim(self) -> int:
        return sum(f.dim for f in CONTEXT_FIELDS)

    @property
    def char_level_dim(self) -> int:
        return sum(f.dim for f in CHAR_LEVEL_FIELDS)

    @property
    def legacy_compat_dim(self) -> int:
        return self.n_features_compat if self.include_legacy_compat else 0

    @property
    def field_offsets(self) -> dict[str, int]:
        """字段名 -> 在 dense 向量中的起始下标（自洽性由单测守护）。

        启用 include_legacy_compat 时，兼容块字段**接在末尾**，偏移随之延伸。
        """
        off: dict[str, int] = {}
        cur = 0
        fields = ALL_DENSE_FIELDS + (LEGACY_COMPAT_FIELDS if self.include_legacy_compat else ())
        for f in fields:
            off[f.name] = cur
            cur += f.dim
        return off

    @property
    def dense_dim(self) -> int:
        """标量向量维度（不含弹幕集合）。"""
        return self.player_dim * 2 + self.relative_dim + self.card_dim \
            + self.skill_dim + self.char_level_dim + self.weather_dim \
            + self.context_dim + self.legacy_compat_dim

    @property
    def bullet_dim(self) -> int:
        return len(BULLET_FIELDS)

    @property
    def total_dim(self) -> int:
        raise NotImplementedError(
            "弹幕是变长集合，不存在固定 'total_dim'。"
            "请分别使用 dense_dim（标量）与 (n_bullets, bullet_dim)（集合）。"
        )

    # ---------------- 来源审计 ----------------
    def unverified_fields(self) -> list[Field]:
        return [f for f in self.fields if f.verify]

    def summary(self) -> dict:
        return {
            "player_dim": self.player_dim, "relative_dim": self.relative_dim,
            "card_dim": self.card_dim, "skill_dim": self.skill_dim,
            "char_level_dim": self.char_level_dim,
            "weather_dim": self.weather_dim, "context_dim": self.context_dim,
            "legacy_compat_dim": self.legacy_compat_dim,
            "dense_dim": self.dense_dim,
            "bullets": {"n": self.n_bullets, "per_object": self.bullet_dim},
            "n_fields": len(self.fields),
            "n_verify": len(self.unverified_fields()),
            "verify_fields": [f.name for f in self.unverified_fields()],
        }

    # ---------------- 向量化 ----------------
    def vectorize(self, raw: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """raw -> (dense (dense_dim,), bullets (K, bullet_dim), bullet_mask (K,))。

        raw 约定：{"self": {字段名: 值}, "opp": {...}, "relative": {...},
                   "cards": {...}, "skills": [15], "weather": {"active": id, "displayed": id,
                   "timer": t, "effect_hidden": 0/1}, "context": {...},
                   "bullets": [{"rel_x":..,"rel_y":..,"rel_vx":..,"rel_vy":..,
                                "direction":..,"action_norm":..}, ...]}
        """
        out: list[float] = []

        def emit(section: dict, fields_: tuple[Field, ...]) -> None:
            for f in fields_:
                if f.dim != 1:
                    raise NotImplementedError(f"暂不支持 dim>1 的字段: {f.name}")
                out.append(f.normalize(float(section.get(f.name, 0.0))))

        emit(raw.get("self", {}), PLAYER_FIELDS)
        emit(raw.get("opp", {}), PLAYER_FIELDS)
        emit(raw.get("relative", {}), RELATIVE_FIELDS)
        emit(raw.get("cards", {}), CARD_FIELDS)

        skills = list(raw.get("skills", []))[:15]
        skills += [0.0] * (15 - len(skills))
        for i, f in enumerate(SKILL_FIELDS):
            out.append(f.normalize(float(skills[i])))

        emit(raw.get("char_levels", {}), CHAR_LEVEL_FIELDS)

        w = raw.get("weather", {})
        act, disp = int(w.get("active", 21)), int(w.get("displayed", 21))
        for i in range(N_WEATHER):
            out.append(1.0 if act == i else 0.0)
        for i in range(N_WEATHER):
            out.append(1.0 if disp == i else 0.0)
        out.append(WEATHER_FIELDS[-3].normalize(float(w.get("timer", 0))))
        out.append(float(w.get("effect_hidden", 0)))
        out.append(1.0 if act != disp else 0.0)

        emit(raw.get("context", {}), CONTEXT_FIELDS)

        if self.include_legacy_compat:
            for f in LEGACY_COMPAT_FIELDS:
                out.append(f.normalize(float(raw.get("legacy_compat", {}).get(f.name[7:], 0.0))))

        dense = np.asarray(out, dtype=np.float32)
        if dense.size != self.dense_dim:
            raise AssertionError(f"向量维度不符: 得到 {dense.size}, 规格 {self.dense_dim}")

        K, D = self.n_bullets, self.bullet_dim
        bullets = np.zeros((K, D), dtype=np.float32)
        mask = np.zeros(K, dtype=np.float32)
        for i, b in enumerate(list(raw.get("bullets", []))[:K]):
            for j, name in enumerate(BULLET_FIELDS):
                v = float(b.get(name, 0.0))
                if name in ("rel_x", "rel_y", "rel_x_opp", "rel_y_opp"):
                    v = np.clip(v / 1200.0, -1.0, 1.0)
                elif name in ("rel_vx", "rel_vy"):
                    v = np.clip(v / 30.0, -1.0, 1.0)
                elif name == "direction":
                    v = float(np.sign(v))
                elif name == "action_norm":
                    v = np.clip(v / ACTION_MAX, 0.0, 1.0)
                elif name == "image_norm":
                    v = np.clip(v / 2000.0, 0.0, 1.0)
                bullets[i, j] = v
            mask[i] = 1.0
        return dense, bullets, mask

    # ---------------- 合成（用于单测 / 信息可得性实验；明确标注为合成） ----------------
    def synthesize(self, rng: np.random.Generator, n_bullets: int | None = None) -> dict:
        """生成一条自洽的合成局面。**这是合成数据，不是真实对局数据。**"""
        k = self.n_bullets if n_bullets is None else n_bullets
        state = float(rng.integers(0, 3))

        def player(prefix: str) -> dict:
            return {
                "hp": float(rng.integers(0, HP_MAX + 1)),
                "spirit": float(rng.integers(0, int(SPIRIT_MAX) + 1)),
                "max_spirit": SPIRIT_MAX,
                "pos_x": float(rng.uniform(0, STAGE_WIDTH)),
                "pos_y": 0.0 if rng.random() < 0.7 else float(rng.uniform(150, 900)),
                "vel_x": float(rng.normal(0, 8)),
                "vel_y": float(rng.normal(0, 5)),
                "facing": 1.0 if rng.random() < 0.5 else -1.0,
                "air_borne": float(rng.random() < 0.4),
                "action": float(rng.integers(0, 800)),
                "pose": float(rng.integers(0, 2000)),
                "pose_frame": float(rng.integers(0, 600)),
                "frame_count": float(rng.integers(0, 600)),
                "sequence": float(rng.integers(0, 999)),
                "hit_stop": float(rng.integers(0, 120)),
                "time_stop": float(rng.integers(0, 120)),
                "untech": float(rng.integers(0, 900)),
                "air_dash_count": float(rng.integers(0, 4)),
                "super_armor_hp": float(rng.normal(0, 500)),
                "combo_damage": float(rng.integers(0, 3001)),
                "combo_limit": float(rng.integers(0, 3001)),
                "guard_frames": float(rng.integers(0, 600)),
                "invuln_frames": float(rng.integers(0, 600)),
                "drop_invul_left": float(rng.integers(0, 1200)),
                "healing_charm": float(rng.integers(0, 251)),
                "confusion": float(rng.integers(0, 900)),
                "sword_of_rapture": float(rng.integers(0, 900)),
                "card_gauge": float(rng.integers(0, 901)),
                "score": float(rng.integers(0, 3)),
                "image": float(rng.integers(0, 2000)),
                "turn_recency": float(rng.integers(0, 600)),
            }

        self_p = player("self")
        opp_p = player("opp")
        dx = opp_p["pos_x"] - self_p["pos_x"]
        dy = opp_p["pos_y"] - self_p["pos_y"]
        hb_ids = [float(rng.integers(0, 221)) if rng.random() < 0.6 else 255.0 for _ in range(5)]
        hb_costs = [float(rng.integers(1, 5)) for _ in range(5)]
        hand_count = sum(1 for i in hb_ids if i != 255)

        return {
            "self": self_p, "opp": opp_p,
            "relative": {
                "dx": dx, "dy": dy, "adx_abs": abs(dx),
                "facing_dx": dx * self_p["facing"],
                "dist_left_corner": self_p["pos_x"],
                "dist_right_corner": STAGE_WIDTH - self_p["pos_x"],
                "dist_front_corner": (STAGE_WIDTH - self_p["pos_x"]) if self_p["facing"] > 0 else self_p["pos_x"],
                "dist_back_corner": self_p["pos_x"] if self_p["facing"] > 0 else (STAGE_WIDTH - self_p["pos_x"]),
                "is_cornered": float(min(self_p["pos_x"], STAGE_WIDTH - self_p["pos_x"]) < 120),
                "opp_cornered": float(min(opp_p["pos_x"], STAGE_WIDTH - opp_p["pos_x"]) < 120),
                "wall_dist": min(self_p["pos_x"], STAGE_WIDTH - self_p["pos_x"]) / 2.0,
            },
            "cards": {
                "hand_count": float(hand_count),
                **{f"hand_id_{i}": hb_ids[i] for i in range(5)},
                **{f"hand_cost_{i}": hb_costs[i] for i in range(5)},
                "selected_slot": float(rng.integers(0, 5)),
                "hand_masked_by_weather": float(rng.random() < 0.1),
                "affordable_count": float(sum(1 for c in hb_costs if c * 100 <= self_p["card_gauge"])),
            },
            "skills": [float(rng.integers(0, 5)) for _ in range(15)],
            "char_levels": {
                "fan_level": float(rng.integers(0, 5)),
                "rods_level": float(rng.integers(0, 5)),
                "books_level": float(rng.integers(0, 5)),
                "doll_level": float(rng.integers(0, 5)),
                "drop_level": float(rng.integers(0, 4)),
            },
            "weather": {
                "active": int(rng.integers(0, N_WEATHER)),
                "displayed": int(rng.integers(0, N_WEATHER)),
                "timer": float(rng.integers(0, 1000)),
                "effect_hidden": float(rng.random() < 0.1),
            },
            "context": {
                "round_index": state,
                "match_timer": float(rng.integers(0, 100)),
                "self_char_norm": float(rng.integers(0, 37)),
                "opp_char_norm": float(rng.integers(0, 37)),
            },
            "bullets": [
                {
                    "rel_x": float(rng.uniform(-1200, 1200)),
                    "rel_y": float(rng.uniform(-800, 800)),
                    "rel_vx": float(rng.normal(0, 12)),
                    "rel_vy": float(rng.normal(0, 12)),
                    "direction": float(rng.choice([-1.0, 1.0])),
                    "action_norm": float(rng.integers(0, 800)),
                }
                for _ in range(int(rng.integers(0, k + 1)))
            ],
        }


__all__ = [
    "Field", "ObservationSpec", "PLAYER_FIELDS", "RELATIVE_FIELDS", "CARD_FIELDS",
    "SKILL_FIELDS", "WEATHER_FIELDS", "CONTEXT_FIELDS", "ALL_DENSE_FIELDS",
    "BULLET_FIELDS", "N_BULLETS", "N_ACTION_CLASS",
    "STAGE_WIDTH", "HP_MAX", "SPIRIT_MAX", "CARD_GAUGE_MAX", "ACTION_MAX",
]
