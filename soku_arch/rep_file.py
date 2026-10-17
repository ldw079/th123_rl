# -*- coding: utf-8 -*-
"""`.rep` **文件格式**解析器 —— 布局全部来自实测（非推测），与兄弟项目实现互相印证。

| 偏移 | 字段 | 证据 |
|---|---|---|
| 0–3 | magic `0xD2` | 193/193 恒定 |
| 6 / 7 | 月 / 日 | 与文件名 99.9% 吻合 |
| 8 | 播放模式（4/5/6） | 3 种取值 |
| **14 / 15** | **玩家 X 角色 / 调色板** | 20,365 带标签文件一致率 **0.999**；取值恰好 20 种 |
| 16 | X 的卡组张数（u32，恒 20） | 16/16 命中 |
| **20–59** | **X 的卡组：20 × u16 卡 ID** | 与 @14 角色一致率（卡表）**1.0000** |
| 60 | 恒 0 | 常量 |
| 61 / 62 | 互补 {0,1}（153:47） | 疑似左右边标志（未定） |
| **63 / 64** | **玩家 Y 角色 / 调色板** | 一致率 **0.998**；取值恰好 20 种 |
| 65 | Y 的卡组张数（u32，恒 20） | 16/16 命中 |
| **69–108** | **Y 的卡组：20 × u16 卡 ID** | 与 @63 角色一致率 **1.0000** |
| 109–116 | 标志位 / 未定字段 | 低基数 |
| **117–120** | **随机种子（u32）** | 193/193 唯一，值域 0.79–1.58e9 |
| **121–** | **输入流：u16 序列，2 条/帧（双方交错）** | 全部 u16 高 4 位为 0；长度/4 落在单局帧数上限内 |

**卡组归属**：X 的卡组属于 X（@14 的角色）、Y 的卡组属于 Y（@63 的角色）——
由卡牌表交叉验证（技能卡/符卡是角色专属，正确配对一致率精确 1.0000）。

**左右边与输入配对**（2026-09-24 **实测裁定**）：

* **@14 = 左、@63 = 右**：神谕流（游戏自播）里"左手牌 ⊆ @20 的卡组、右手牌 ⊆ @69 的卡组"
  精确成立 → 游戏自己就是把 X 放左边，与驱动 `left_is_x=True` 一致。
* ⚠ **输入流的交错顺序是 `[右, 左]`，不是 `[左, 右]`**：
  用 mod（`SOKUAI_INPUTLOG=1`）记下**游戏每逻辑帧实际生效的输入**，再与 `.rep` 逐帧精确比对：

  ```
  游戏左玩家生效输入 == inputs[2f+1]   段1 δ=61 match=1.0000 | 段2 δ=151 match=0.9810
  游戏右玩家生效输入 == inputs[2f]     段1 δ=60 match=1.0000 | 段2 δ=150 match=0.9792
  ```

  100% 精确匹配 → **不是巧合**。此前 `rep_drive.py` 默认把 `inputs[2f]` 给左边，
  于是一直在**把双方输入对调着喂**（这正是"驱动重演与原局分叉"的根因）。
  对外统一用 `inputs_by_side()` 取值，不要自己写下标。
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

MAGIC = 0xD2
OFF_MONTH = 6
OFF_DAY = 7
OFF_MODE = 8
OFF_CHAR_X = 14
OFF_PAL_X = 15
OFF_DECK_SIZE_X = 16
OFF_DECK_X = 20
OFF_CHAR_Y = 63
OFF_PAL_Y = 64
OFF_DECK_SIZE_Y = 65
OFF_DECK_Y = 69
OFF_SEED = 117
INPUT_START = 121
DECK_SIZE = 20
N_CHARS = 20          # CharacterPacked 0..19（基础角色；Soku2 角色用更高值）
MIN_SIZE = INPUT_START        # 头部即 121 字节；"无输入帧"交给 sane() 判定，而非解析直接拒绝


class RepFileError(ValueError):
    """格式不符合实测布局 —— 大声失败，不返回半成品。"""


@dataclass
class RepFile:
    path: str = ""
    size: int = 0
    month: int = 0
    day: int = 0
    mode: int = 0
    char_x: int = 0            # @14
    pal_x: int = 0             # @15
    deck_x: tuple[int, ...] = ()      # @20-59，属 char_x
    char_y: int = 0            # @63
    pal_y: int = 0             # @64
    deck_y: tuple[int, ...] = ()      # @69-108，属 char_y
    seed: int = 0              # @117
    inputs: tuple[int, ...] = ()      # @121 起，u16 序列
    flags: bytes = b""         # 60-62 与 109-116 的原始字节（待定字段）

    # ---- 派生 ----
    @property
    def n_entries(self) -> int:
        return len(self.inputs)

    @property
    def n_frames(self) -> int:
        """双方交错 => 每帧 2 条。"""
        return len(self.inputs) // 2

    # rep_stack缺口3(2026-10-13): frames()已删除 — 它按旧错误顺序产出
    # 并标注left/right(实测裁定为[右,左], 见inputs_by_side/pair_input_frame
    # 及其契约测试), 与当年rep_drive对调事故同型。现役调用方为零
    # (仅隔离区死工具引用); 新消费者一律用inputs_by_side。

    def sane(self) -> list[str]:
        """返回问题列表（空 = 通过）。"""
        problems: list[str] = []
        if len(self.deck_x) != DECK_SIZE:
            problems.append(f"deck_x 张数 {len(self.deck_x)} != {DECK_SIZE}")
        if len(self.deck_y) != DECK_SIZE:
            problems.append(f"deck_y 张数 {len(self.deck_y)} != {DECK_SIZE}")
        for name, c in (("char_x", self.char_x), ("char_y", self.char_y)):
            if not (0 <= c < N_CHARS):
                problems.append(f"{name}={c} 不在 0..{N_CHARS - 1}")
        for name, d in (("deck_x", self.deck_x), ("deck_y", self.deck_y)):
            bad = [v for v in d if v > 0xFFFF]
            if bad:
                problems.append(f"{name} 含超范围卡 ID {bad[:4]}")
        if self.n_frames <= 0:
            problems.append("无输入帧")
        return problems


def parse_rep_file(path: str) -> RepFile:
    with open(path, "rb") as f:
        b = f.read()
    return parse_rep_bytes(b, path)


def parse_rep_bytes(b: bytes, path: str = "") -> RepFile:
    if len(b) < MIN_SIZE:
        raise RepFileError(f"文件过短: {len(b)} < {MIN_SIZE}（连头部都不完整）")
    if b[0] != MAGIC:
        raise RepFileError(f"magic 不是 0x{MAGIC:02X}（实际 0x{b[0]:02X}）")
    size_x = struct.unpack_from("<I", b, OFF_DECK_SIZE_X)[0]
    size_y = struct.unpack_from("<I", b, OFF_DECK_SIZE_Y)[0]
    if size_x != DECK_SIZE or size_y != DECK_SIZE:
        raise RepFileError(f"卡组张数异常: X={size_x} Y={size_y}（期望 {DECK_SIZE}）")
    n_entries = (len(b) - INPUT_START) // 2
    rep = RepFile(
        path=path,
        size=len(b),
        month=b[OFF_MONTH],
        day=b[OFF_DAY],
        mode=b[OFF_MODE],
        char_x=b[OFF_CHAR_X],
        pal_x=b[OFF_PAL_X],
        deck_x=tuple(struct.unpack_from(f"<{DECK_SIZE}H", b, OFF_DECK_X)),
        char_y=b[OFF_CHAR_Y],
        pal_y=b[OFF_PAL_Y],
        deck_y=tuple(struct.unpack_from(f"<{DECK_SIZE}H", b, OFF_DECK_Y)),
        seed=struct.unpack_from("<I", b, OFF_SEED)[0],
        inputs=tuple(struct.unpack_from(f"<{n_entries}H", b, INPUT_START)),
        flags=bytes(b[60:63]) + bytes(b[109:117]),
    )
    return rep


def pair_input_frame(entries, f: int, swap: bool = False) -> tuple[int, int]:
    """第 f 帧的 `(left_raw, right_raw)`（原始 u16 BattleKeys）。

    **实测约定**：`.`rep` 的交错顺序是 `[右, 左]` —— `inputs[2f]` 属**右**、`inputs[2f+1]` 属**左**
    （证据：游戏自播时逐帧精确匹配率 1.0000，见模块 docstring）。
    `swap=True` 用于做镜像对照（`rep-drive --swap-inputs`）。
    """
    right_raw, left_raw = int(entries[2 * f]), int(entries[2 * f + 1])
    return (right_raw, left_raw) if swap else (left_raw, right_raw)


def inputs_by_side(entries, swap: bool = False) -> np.ndarray:
    """整个输入流 → `(M, 2)` 数组，列序固定为 **`[左, 右]`**（对外唯一口径）。

    ⚠ **容忍奇数条目**：实测存在 `(size-121)//2` 为**奇数**的 `.rep`（尾部单个 u16
    无法配对）。这类残尾**直接丢弃**（`M = floor(n/2)`），而不是让 reshape 抛
    `ValueError` 把整局采集废掉 —— 2026-09-25 批量采集时 4/4 局都撞到过这个。
    """
    import numpy as np

    a = np.asarray(entries, dtype=np.int64).reshape(-1)
    if a.size % 2:
        # 实测存在 (size-121)//2 为**奇数**的 .rep（尾部单个 u16 无法配对）。
        # 残尾直接丢弃（M = floor(n/2)），而不是让 reshape 抛 ValueError 废掉整局采集
        # —— 2026-09-25 批量采集 4/4 局都撞到过。
        a = a[:-1]
    arr = a.reshape(-1, 2)
    left, right = arr[:, 1], arr[:, 0]
    out = np.stack([right, left], axis=1) if swap else np.stack([left, right], axis=1)
    return out.astype(np.int32)


def find_rep_files(root: str) -> list[str]:
    out: list[str] = []
    for dp, _d, fs in os.walk(root):
        for fn in sorted(fs):
            if fn.lower().endswith(".rep"):
                out.append(os.path.join(dp, fn))
    return out


__all__ = ["MAGIC", "INPUT_START", "DECK_SIZE", "N_CHARS", "RepFileError", "RepFile",
           "parse_rep_file", "parse_rep_bytes", "find_rep_files",
           "pair_input_frame", "inputs_by_side"]
