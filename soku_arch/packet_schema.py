# -*- coding: utf-8 -*-
"""权威包结构：部署端状态包（105 字节/玩家）的**可校验**定义与对账工具。

来源（只读复制，带文件行号）：
  C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\soku_client2.py:39-57
     CS_FIELDS  35 个字段
     CS_FMT     "<b2fHHHHIHH?HHHBHHHHHHB10sH15sBBBBBHHH20sB"
     CS_SIZE    struct.calcsize(CS_FMT)   == 105
     FRAME_HEAD = 1 + CS_SIZE*2 + 4        （op + 两玩家 + 天气 4 字节）
  D:\\temp\\build\\SokuAI-master\\...\\packet.hpp:110-158（`CharacterState`）
     —— 注意：这是 **SokuAI-master 血统**的另一套包（含 `opponentRelativePos`、
     `distToGround`、`csd` 等价计时器等），与实际部署的 TrainingMod 血统
     **不是同一个 wire format**。混用两者会得到错误字段语义（本项目曾把两套混着引用）。

为什么要把它做成规格并与观测规格对账：
  前序项目反复出现"文档与代码相反"（第 3 列特征名、手抄魔数、注释与实现不符）。
  把 wire format 变成**机器可校验**的数据结构后，"模型用了不存在的字段"或
  "包里传了但一直没用的字段"都能被工具直接点出来，而不是靠人读代码。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# --------------------------------------------------------------------------
# 权威字段与格式（逐字复制，勿改）
# --------------------------------------------------------------------------
CS_FIELDS: tuple[str, ...] = (
    "direction", "position.x", "position.y",
    "action", "sequence", "pose", "poseFrame",
    "frameCount", "comboDamage", "comboLimit",
    "airBorne", "timeStop", "hitStop",
    "hp", "airDashCount", "spirit", "maxSpirit",
    "untech", "healingCharm", "confusion", "swordOfRapture",
    "score",
    "hand",            # 10 字节: 5×(id,cost)
    "cardGauge",
    "skills",          # 15 字节
    "fanLevel", "rodsLevel", "booksLevel", "dollLevel", "dropLevel",
    "dropInvulTimeLeft", "superArmorHp", "imageID",
    "csd",             # 20 字节 角色特异数据 —— 已传输但**从未被解析**
    "objectCount",
)
CS_FMT: str = "<b2fHHHHIHH?HHHBHHHHHHB10sH15sBBBBBHHH20sB"
CS_SIZE: int = struct.calcsize(CS_FMT)
FRAME_HEAD: int = 1 + CS_SIZE * 2 + 4

# 每个字段的 (struct 代码, 字节数)，顺序与 CS_FIELDS 严格一致
_SPEC: tuple[tuple[str, str, int], ...] = (
    ("direction", "b", 1),
    ("position.x", "f", 4), ("position.y", "f", 4),
    ("action", "H", 2), ("sequence", "H", 2), ("pose", "H", 2), ("poseFrame", "H", 2),
    ("frameCount", "I", 4),
    ("comboDamage", "H", 2), ("comboLimit", "H", 2),
    ("airBorne", "?", 1),
    ("timeStop", "H", 2), ("hitStop", "H", 2), ("hp", "H", 2),
    ("airDashCount", "B", 1),
    ("spirit", "H", 2), ("maxSpirit", "H", 2), ("untech", "H", 2),
    ("healingCharm", "H", 2), ("confusion", "H", 2), ("swordOfRapture", "H", 2),
    ("score", "B", 1),
    ("hand", "10s", 10),
    ("cardGauge", "H", 2),
    ("skills", "15s", 15),
    ("fanLevel", "B", 1), ("rodsLevel", "B", 1), ("booksLevel", "B", 1),
    ("dollLevel", "B", 1), ("dropLevel", "B", 1),
    ("dropInvulTimeLeft", "H", 2), ("superArmorHp", "H", 2), ("imageID", "H", 2),
    ("csd", "20s", 20),
    ("objectCount", "B", 1),
)

# 包的常规取值范围（用于归一化；来源 [E] Env.py 的 Bounded 与 [F] feat_builder 的除数）
FIELD_RANGE: dict[str, tuple[float, float]] = {
    "direction": (-1, 1), "position.x": (-900, 2200), "position.y": (-100, 2200),
    "action": (0, 799), "sequence": (0, 999), "pose": (0, 2000), "poseFrame": (0, 600),
    "frameCount": (0, 600), "comboDamage": (0, 3000), "comboLimit": (0, 3000),
    "airBorne": (0, 1), "timeStop": (0, 120), "hitStop": (0, 120), "hp": (0, 10000),
    "airDashCount": (0, 3), "spirit": (0, 2000), "maxSpirit": (0, 2000),
    "untech": (0, 900), "healingCharm": (0, 250), "confusion": (0, 900),
    "swordOfRapture": (0, 900), "score": (0, 2), "cardGauge": (0, 900),
    "fanLevel": (0, 4), "rodsLevel": (0, 4), "booksLevel": (0, 4),
    "dollLevel": (0, 4), "dropLevel": (0, 3),
    "dropInvulTimeLeft": (0, 1200), "superArmorHp": (-10000, 10000),
    "imageID": (0, 2000), "objectCount": (0, 48),
}

# 已传输但当前观测**仍未使用**的字段（白送的信息）。
# 只列**部署端包内真实存在**的字段：`actionBlockId`/`animate` 只存在于 packet.hpp 的
# 另一血统，不在 CS_FIELDS 里，不能列在这里（否则审计会给出无法兑现的建议）。
# 说明：五个 char level 与 objectCount 已在本轮并入观测规格，故不再列入；
# 剩下 `csd`（20 字节/玩家，角色特异）是唯一的"已传输但从未解析"字段。
UNUSED_IN_CURRENT_OBS: tuple[str, ...] = ("csd",)


@dataclass(frozen=True)
class FieldLayout:
    name: str
    offset: int
    size: int
    code: str
    lo: float
    hi: float


def field_layout() -> tuple[FieldLayout, ...]:
    """逐字段的字节偏移（自洽性由单测守护：偏移连续且总和 == CS_SIZE）。"""
    out, off = [], 0
    for (name, code, size), declared in zip(_SPEC, CS_FIELDS):
        if name != declared:
            raise AssertionError(f"字段顺序不一致: layout={name} CS_FIELDS={declared}")
        lo, hi = FIELD_RANGE.get(name, (0.0, 1.0))
        out.append(FieldLayout(name, off, size, code, lo, hi))
        off += size
    return tuple(out)


def packet_size() -> int:
    return CS_SIZE


def normalize(name: str, value: float) -> float:
    lo, hi = FIELD_RANGE.get(name, (0.0, 1.0))
    if hi == lo:
        return 0.0
    return float(min(1.0, max(0.0, (value - lo) / (hi - lo))))


def unpack_player(buf: bytes) -> dict:
    """把 105 字节解码成 {字段名: 值}。纯 struct，无需游戏进程即可测试。

    * `hand` -> (id, cost) × 5；0xFF 表示空槽（与 mod 的哨兵一致）
    * `skills` -> 15 个等级
    * `csd` -> 原始 20 字节（**未解码**，需要按角色表解释）
    """
    if len(buf) != CS_SIZE:
        raise ValueError(f"玩家状态应为 {CS_SIZE} 字节，实际 {len(buf)}")
    vals = struct.unpack(CS_FMT, buf)
    out: dict = {}
    for layout, v in zip(field_layout(), vals):
        if layout.name == "hand":
            out["hand"] = [(buf[layout.offset + i * 2], buf[layout.offset + i * 2 + 1])
                           for i in range(5)]
        elif layout.name == "skills":
            out["skills"] = list(buf[layout.offset: layout.offset + 15])
        elif layout.name == "csd":
            out["csd"] = bytes(buf[layout.offset: layout.offset + 20])
        else:
            out[layout.name] = v
    return out


def pack_player(d: dict) -> bytes:
    """packet_player 的逆操作（测试与合成数据用）。"""
    parts: list[bytes] = []
    for layout in field_layout():
        name = layout.name
        if name == "hand":
            arr = bytearray(10)
            for i, (cid, cost) in enumerate(d.get("hand", [(0xFF, 0xFF)] * 5)):
                arr[i * 2], arr[i * 2 + 1] = cid & 0xFF, cost & 0xFF
            parts.append(bytes(arr))
        elif name == "skills":
            sk = bytes(list(d.get("skills", [0] * 15)))[:15]
            parts.append(sk.ljust(15, b"\x00"))
        elif name == "csd":
            parts.append(bytes(d.get("csd", b"\x00" * 20))[:20].ljust(20, b"\x00"))
        else:
            parts.append(struct.pack(layout.code, d.get(name, 0)))
    blob = b"".join(parts)
    if len(blob) != CS_SIZE:
        raise AssertionError(f"打包结果 {len(blob)} != {CS_SIZE}")
    return blob


# 观测规格字段名 -> 包字段名（命名不同但语义相同；缺失别名会产生假的"字段不存在"告警，
# 而吵的审计等于没有审计）
FIELD_ALIASES: dict[str, str] = {
    "pos_x": "position.x", "pos_y": "position.y",
    "facing": "direction",
    "image": "imageID",
    "drop_invul_left": "dropInvulTimeLeft",
    "super_armor_hp": "superArmorHp",
}


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


# --------------------------------------------------------------------------
# 与观测规格对账
# --------------------------------------------------------------------------
def reconcile(spec_field_names: set[str], obs_bullet_fields: tuple[str, ...] = ()) -> dict:
    """把**观测规格**与 wire format 对账。

    返回三类问题：
      * `spec_fields_not_in_packet`：模型用了包里没有、也不属于派生量的字段
        （必须标"需 mod 补"或删掉，否则等于凭空造特征）
      * `packet_fields_unused`：包里传了但观测没用（白送的信息）
      * `derived`：包里没有、由客户端派生（速度差值、角距、角标志等）—— 必须显式标注
    名称匹配做**归一化**（去大小写与非字母数字）并走别名表，避免假告警。
    """
    packet_norm = {_norm(f.name): f.name for f in field_layout()}
    packet_norm[_norm("objects")] = "objects"
    packet_names = {f.name for f in field_layout()} | {"objects"}
    # 观测规格里"派生"性质的字段（不在包里，靠差分/组合/其他包得到）
    derived = {"vel_x", "vel_y", "rel_vx", "rel_vy", "rel_x", "rel_y",
               "rel_x_opp", "rel_y_opp", "dist_left_corner", "dist_right_corner",
               "dist_front_corner", "dist_back_corner",
               "is_cornered", "opp_cornered", "cornered",
               "wall_dist", "dx", "dy", "adx_abs", "facing_dx", "turn_recency",
               "guard_frames", "invuln_frames", "match_timer", "affordable_count",
               "hand_count", "selected_slot", "hand_masked_by_weather",
               "weather_effect_hidden", "weather_mismatch", "round_index",
               "self_char_norm", "opp_char_norm", "char_norm", "legacy_compat",
               "opp_air", "air"}
    # 派生字段的**前缀**（成组出现，逐个列会漏）
    derived_prefixes = ("hand_id_", "hand_cost_", "legacy_", "weather_", "skill_",
                        "fan_level", "rods_level", "books_level", "doll_level",
                        "drop_level")
    norm_derived = {_norm(d) for d in derived} | {_norm(d) for d in derived_prefixes}

    def base(n: str) -> str:
        for p in ("self_", "opp_"):
            if n.startswith(p):
                return n[len(p):]
        return n

    def is_derived(n: str, b: str) -> bool:
        return (b in derived or n in derived
                or _norm(b) in norm_derived or _norm(n) in norm_derived
                or b.startswith(derived_prefixes) or n.startswith(derived_prefixes))

    not_in_packet, accounted = [], []
    for n in sorted(spec_field_names):
        b = base(n)
        alias = FIELD_ALIASES.get(b, b)
        if is_derived(n, b):
            accounted.append(n)
        elif alias in packet_names or _norm(alias) in packet_norm:
            accounted.append(n)
        else:
            not_in_packet.append(n)

    unused = [f.name for f in field_layout() if f.name in UNUSED_IN_CURRENT_OBS]
    return {
        "packet_size": CS_SIZE,
        "n_packet_fields": len(CS_FIELDS),
        "n_spec_fields": len(spec_field_names),
        "n_accounted": len(accounted),
        "spec_fields_not_in_packet": not_in_packet,
        "packet_fields_unused": unused,
        "packet_fields_unused_note":
            "这些字段**已在传输但当前观测未使用**。本轮已把五个 char level 与 objectCount "
            "并入观测规格，因此只剩下 csd（20 字节×2 玩家角色特异数据）—— "
            "这是当前唯一的'零成本信息增量'，需要按角色表解码。",
        "frame_packet_gaps_note": (
            "帧包内**没有角色 ID**（需从 StartGame 参数带入，属另一条数据通路）；"
            "帧包内也**没有速度、角距、distToGround** —— 全部需要派生。"
        ),
        "bullet_note": (
            "包里 Object 只有 direction / relativePosMe / relativePosOpponent / action / imageID；"
            "**速度不在包里**，旧实现靠逐帧差分（feat_builder.py:77-104 按 seq 匹配）求出，"
            "会出现新弹速度=0、丢帧时速度错误等问题 —— 属于派生字段，必须显式标注。"
        ),
        "obs_bullet_fields": list(obs_bullet_fields),
    }


__all__ = [
    "CS_FIELDS", "CS_FMT", "CS_SIZE", "FRAME_HEAD", "FIELD_RANGE",
    "UNUSED_IN_CURRENT_OBS", "FIELD_ALIASES", "FieldLayout", "field_layout",
    "packet_size", "unpack_player", "pack_player", "normalize", "reconcile",
]
