# -*- coding: utf-8 -*-
"""帧级输入编解码（路线 B：不做宏抽象，直接学逐帧输入）。

**关键点：非想天则里存在两套不同的输入编码，不能混用。**

| 编码 | 定义来源 | 位宽 | 字段 |
|---|---|---|---|
| `BattleKeys` / `Inputs` | `SokuLib/src/InputManager.hpp:66-84` | u16 位域 12 位 | up, down, left, right, A, B, C, **dash**, AandB, BandC, pause, select |
| `Trainer::Input` | `packet.hpp:160-172`（mod 包） | u16 位域 10 位 | A, B, C, D, SC, SW, **H(2bit)**, V(2bit) |

* replay 与游戏内部用的是**前者**（方向是 4 个独立位、有 dash/AandB/BandC）
* 训练 mod 的状态包用的是**后者**（方向被压成 H/V 两个 2 位有符号值）

因此"从 replay 读专家输入 → 与 mod 回放时记录的输入对齐"必须经过一次显式转换，
而转换里唯一不能凭猜的是 `AandB`/`BandC` 到 `SC`/`SW` 的对应关系 —— 故本模块
**保留全部原始位**，把派生标记单独输出并标 TO_VERIFY，绝不静默丢弃。

动作空间：方向 9 值（numpad 1-9，5=中立）× 按键掩码 16（A/B/C/dash）= **144**，
与架构文档里的联合动作空间一致；另附两个组合键位（AandB/BandC）作为附加位。
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# BattleKeys / Inputs（游戏内部与 replay）
# --------------------------------------------------------------------------
BATTLE_BITS: tuple[str, ...] = (
    "up", "down", "left", "right",          # 0..3
    "A", "B", "C", "dash",                  # 4..7
    "AandB", "BandC", "pause", "select",    # 8..11
)
BATTLE_BIT_INDEX: dict[str, int] = {n: i for i, n in enumerate(BATTLE_BITS)}

# Trainer::Input（mod 状态包）
TRAINER_BITS: tuple[str, ...] = ("A", "B", "C", "D", "SC", "SW")
TRAINER_BIT_INDEX: dict[str, int] = {n: i for i, n in enumerate(TRAINER_BITS)}

BTN_NAMES: tuple[str, ...] = ("A", "B", "C", "dash")   # 4 位掩码
DIR_NAMES: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "8", "9")  # numpad


def _bits(value: int, names: tuple[str, ...], base: int = 0) -> dict[str, bool]:
    return {n: bool((int(value) >> (base + i)) & 1) for i, n in enumerate(names)}


# --------------------------------------------------------------------------
@dataclass(frozen=True)
class BattleInput:
    """游戏内部 / replay 的输入（12 位，全部保留）。"""

    raw: int

    @classmethod
    def from_bits(cls, **kw: bool) -> "BattleInput":
        v = 0
        for k, val in kw.items():
            if k not in BATTLE_BIT_INDEX:
                raise KeyError(f"未知按键位: {k}")
            if val:
                v |= 1 << BATTLE_BIT_INDEX[k]
        return cls(v)

    @property
    def up(self) -> bool: return bool(self.raw >> 0 & 1)
    @property
    def down(self) -> bool: return bool(self.raw >> 1 & 1)
    @property
    def left(self) -> bool: return bool(self.raw >> 2 & 1)
    @property
    def right(self) -> bool: return bool(self.raw >> 3 & 1)
    @property
    def buttons(self) -> tuple[bool, bool, bool, bool]:
        return (bool(self.raw >> 4 & 1), bool(self.raw >> 5 & 1),
                bool(self.raw >> 6 & 1), bool(self.raw >> 7 & 1))

    def as_dict(self) -> dict[str, bool]:
        return _bits(self.raw, BATTLE_BITS)

    @property
    def hv(self) -> tuple[int, int]:
        """→ (H, V)：H: -1 左 / +1 右；V: -1 上 / +1 下。

        注意"同时按下相反方向"的处理：本函数返回两者之差，
        同时按下时为 0（中立）。原版是否另有优先级规则**未验证**，标 TO_VERIFY。
        """
        h = (1 if self.right else 0) - (1 if self.left else 0)
        v = (1 if self.down else 0) - (1 if self.up else 0)
        return h, v

    @property
    def direction(self) -> int:
        """numpad 方向 1..9（5 = 中立）。"""
        return hv_to_dir(*self.hv)

    @property
    def button_mask(self) -> int:
        m = 0
        for i, b in enumerate(self.buttons):
            if b:
                m |= 1 << i
        return m

    @property
    def joint_index(self) -> int:
        """144 联合动作下标 = (方向-1)*16 + 按键掩码。"""
        return (self.direction - 1) * 16 + self.button_mask


def hv_to_dir(h: int, v: int) -> int:
    """(H, V) → numpad 方向。V 为 -1 上 / +1 下（与 Trainer::Input 的 V 同号）。"""
    table = {
        (-1, -1): 7, (0, -1): 8, (1, -1): 9,
        (-1, 0): 4, (0, 0): 5, (1, 0): 6,
        (-1, 1): 1, (0, 1): 2, (1, 1): 3,
    }
    if (h, v) not in table:
        raise ValueError(f"非法 (H,V)=({h},{v})；取值应为 -1/0/1")
    return table[(h, v)]


def dir_to_hv(direction: int) -> tuple[int, int]:
    for (h, v), d in {(-1, -1): 7, (0, -1): 8, (1, -1): 9, (-1, 0): 4, (0, 0): 5,
                      (1, 0): 6, (-1, 1): 1, (0, 1): 2, (1, 1): 3}.items():
        if d == direction:
            return h, v
    raise ValueError(f"非法方向: {direction}（应为 1..9）")


def _signed2(x: int) -> int:
    """2 位有符号（MSVC 位域 char:2）→ -2..1。"""
    x &= 0b11
    return x - 4 if x >= 2 else x


def _pack_signed2(x: int) -> int:
    if x not in (-2, -1, 0, 1):
        raise ValueError(f"2 位有符号字段只能取 -2..1，得到 {x}")
    return x & 0b11


@dataclass(frozen=True)
class TrainerInput:
    """mod 状态包里的输入（10 位）。"""

    raw: int

    @property
    def A(self) -> bool: return bool(self.raw >> 0 & 1)
    @property
    def B(self) -> bool: return bool(self.raw >> 1 & 1)
    @property
    def C(self) -> bool: return bool(self.raw >> 2 & 1)
    @property
    def D(self) -> bool: return bool(self.raw >> 3 & 1)
    @property
    def SC(self) -> bool: return bool(self.raw >> 4 & 1)
    @property
    def SW(self) -> bool: return bool(self.raw >> 5 & 1)
    @property
    def H(self) -> int: return _signed2((self.raw >> 6) & 0b11)
    @property
    def V(self) -> int: return _signed2((self.raw >> 8) & 0b11)

    @classmethod
    def from_fields(cls, A=False, B=False, C=False, D=False, SC=False, SW=False,
                    H: int = 0, V: int = 0) -> "TrainerInput":
        v = 0
        for i, b in enumerate((A, B, C, D, SC, SW)):
            if b:
                v |= 1 << i
        v |= _pack_signed2(H) << 6
        v |= _pack_signed2(V) << 8
        return cls(v)

    def as_dict(self) -> dict:
        return {"A": self.A, "B": self.B, "C": self.C, "D": self.D,
                "SC": self.SC, "SW": self.SW, "H": self.H, "V": self.V}

    @property
    def direction(self) -> int:
        return hv_to_dir(self.H, self.V)

    @property
    def button_mask(self) -> int:
        return (int(self.A) | (int(self.B) << 1) | (int(self.C) << 2) | (int(self.D) << 3))


# --------------------------------------------------------------------------
# 两套编码之间的转换
# --------------------------------------------------------------------------
def battle_to_trainer(b: BattleInput) -> tuple[TrainerInput, dict]:
    """BattleKeys → Trainer::Input。

    返回 (转换结果, 备注)。**有损/未证实之处全部放进备注**，不静默丢弃：
      * dash → D 是直接对应（两者都是"冲刺/飞翔"键）
      * AandB / BandC 在 Trainer 编码里没有独立位；本函数按"组合键 → SC"的
        常见解释映射 AandB→SC，并把 BandC 与 pause/select 列入未映射位。
        AandB→SC 已实证(2026-10-13, rep_stack缺口1): oracle shards 48片
        交叉验证, AandB上升沿×手牌差分事件(±3帧) 吻合 238/248=96.0%
        (随机对照2.0%; 逐帧口径67.1%系按住帧稀释)。证据:
        th123_rl /d/temp/aandb_edge.txt + METHODOLOGY 2.93
      * 方向同时按下相反键时取差值（见 BattleInput.hv 的 TO_VERIFY）
    """
    notes: dict = {"unmapped_bits": [], "assumptions": []}
    d = b.as_dict()
    sc = False
    if d.get("AandB"):
        sc = True
        notes["assumptions"].append("AandB → SC（已实证96.0%, 2026-10-13）")
    for k in ("BandC", "pause", "select"):
        if d.get(k):
            notes["unmapped_bits"].append(k)
    H, V = b.hv
    return TrainerInput.from_fields(A=d["A"], B=d["B"], C=d["C"], D=d["dash"],
                                    SC=sc, SW=False, H=H, V=V), notes


def trainer_to_battle(t: TrainerInput) -> BattleInput:
    """Trainer::Input → BattleKeys（方向位按 H/V 展开）。"""
    H, V = t.H, t.V
    if H == -2 or V == -2:
        # -2 在 2 位有符号里是合法位型但语义未证实；不静默当成 0
        raise ValueError(f"Trainer::Input 的方向位出现未证实的 -2（H={H}, V={V}）")
    b = BattleInput.from_bits(
        up=V < 0, down=V > 0, left=H < 0, right=H > 0,
        A=t.A, B=t.B, C=t.C, dash=t.D,
    )
    if t.SC:
        # SC 无法唯一还原为 AandB（也可能来自其他来源）—— 用 AandB 位表示并标注
        b = BattleInput(b.raw | (1 << BATTLE_BIT_INDEX["AandB"]))
    return b


def joint_index_to_battle(idx: int) -> BattleInput:
    """144 联合动作下标 → BattleInput（仅方向+四键位，无组合键）。"""
    if not (0 <= idx < 144):
        raise ValueError(f"联合动作下标越界: {idx}")
    direction, mask = divmod(int(idx), 16)
    h, v = dir_to_hv(direction + 1)
    return BattleInput.from_bits(
        up=v < 0, down=v > 0, left=h < 0, right=h > 0,
        A=bool(mask >> 0 & 1), B=bool(mask >> 1 & 1),
        C=bool(mask >> 2 & 1), dash=bool(mask >> 3 & 1),
    )


ACTION_SPACE_SIZE = 144


__all__ = [
    "BATTLE_BITS", "BATTLE_BIT_INDEX", "TRAINER_BITS", "TRAINER_BIT_INDEX",
    "BTN_NAMES", "DIR_NAMES", "ACTION_SPACE_SIZE",
    "BattleInput", "TrainerInput", "hv_to_dir", "dir_to_hv",
    "battle_to_trainer", "trainer_to_battle", "joint_index_to_battle",
]
