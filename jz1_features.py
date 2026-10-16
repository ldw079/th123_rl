# -*- coding: utf-8 -*-
"""JZ-1 预制件(2026-10-14): A档字段特征的计算器与段位规范 — **未接线**。

接线(迁移窗)时在feat_builder追加: CORE_DIMS 343→358 + build()尾部调用
本模块fill_jz1()。本模块独立可测, 不import feat_builder(零循环风险)。

15维规范(docs/_reviews/jz_field_semantics_probe_2026-10-14.md裁定):
  [343] 我方airDashCount(/3)      [344] 对手airDashCount(/3)
  [345] 我方灵力冷却剩余(/120)     [346] 对手灵力冷却剩余(/120)
  [347] 我方comboLimit(/100)       [348] 对手comboLimit(/100)
  [349] 我方已升级技能数(/4)       [350] 我方技能最高等级(/4)
  [351] 对手已升级技能数(/4)       [352] 对手技能最高等级(/4)
  [353] 我方破珠数(/3)             [354] 对手破珠数(/3)
  [355] 对手蹲姿(0/1)              [356] 对手hitStop(0/1)
  [357] healingCharm(0/1, 双侧或)

近似声明(攻略数值纪律 — 显式不猜):
  - 灵力冷却分类: 动作400-432=B/C射混区(枚举文档§1), 无法按段分B(45F)/
    C(60F) — v1统一60F(保守高估=特征更晚解锁); 必杀500-593=120F;
    帕秋莉(4)专属40/48/60。B/C精确分类=hitlab后续工作。
  - 破珠数 = maxSpirit/200 - 2 (值域400..1000 → 0..3珠破)。
"""
from __future__ import annotations

# ---- 灵力冷却表(data/guide_tables/spirit_cooldown.json, 2026-10-14) ----
COOLDOWN_SHOT = 60          # B/C统一(保守; 精确B=45/C=60待hitlab分表)
COOLDOWN_SKILL = 120        # 必杀(大部分)
PATCHOULI_OVERRIDE = {'shot': 48, 'skill': 60}   # 帕秋莉(char_id=4)专属

SHOT_RANGE = (400, 432)     # B/C系(含jB/jC/66B/66C) — 枚举文档§1
SKILL_RANGE = (500, 593)    # 必杀技(默认/ALT1/ALT2×4形态)


def cooldown_frames(action: int, char_id: int) -> int:
    """该动作触发的灵力回复冷却帧数(0=不触发)。"""
    cd_shot = (PATCHOULI_OVERRIDE['shot'] if char_id == 4
               else COOLDOWN_SHOT)
    cd_skill = (PATCHOULI_OVERRIDE['skill'] if char_id == 4
                else COOLDOWN_SKILL)
    if SHOT_RANGE[0] <= action <= SHOT_RANGE[1]:
        return cd_shot
    if SKILL_RANGE[0] <= action <= SKILL_RANGE[1]:
        return cd_skill
    return 0


class SpiritCooldownTracker:
    """逐帧喂"该侧动作+char_id", 读剩余冷却(/1, 归一由fill层做)。

    frozen帧(hitstop/SC暗转)不推进 — 攻略: 冷却期HITSTOP/暗转不计
    (spirit_cooldown.json recovery.no_recovery_during的同拍处理)。
    新动作进入射击/必杀段边沿时重置冷却(连续出招刷新)。
    """

    def __init__(self):
        self.remaining = 0
        self._last_action = -1

    def feed(self, action: int, char_id: int, frozen: bool = False):
        if frozen:
            return
        cd = cooldown_frames(action, char_id)
        # 边沿进入(或段内持续)都刷新 — 出招动作持续多帧, 每帧刷新无害
        if cd:
            self.remaining = max(self.remaining, cd)
        self._last_action = action
        if self.remaining > 0:
            self.remaining -= 1

    @property
    def value(self) -> float:
        return self.remaining / 120.0


def skills_summary(skills_bytes) -> tuple:
    """15字节技能槽 → (已升级数, 最高等级)。JZ-0证实: byte4-11=8槽,
    0xFF=空, 值∈{1,2}=等级; 0=未升级槽(防御性同空处理)。"""
    if not skills_bytes or len(skills_bytes) < 12:
        return (0, 0)
    slots = skills_bytes[4:12]
    lv = [b for b in slots if b not in (0, 0xFF)]
    return (len(lv), max(lv) if lv else 0)


def orb_broken_norm(max_spirit) -> float:
    """maxSpirit{400,600,800,1000} → 已破珠数/3 (0..1)。
    珠数=maxSpirit/200(满5珠=1000) → 破珠数=5−珠数(0..3)。"""
    try:
        v = int(max_spirit)
    except (TypeError, ValueError):
        return 0.0
    if v < 400 or v > 1000:
        return 0.0
    return (5.0 - v / 200.0) / 3.0


def fill_jz1(out, base, left: dict, right: dict,
             my_cd: SpiritCooldownTracker, opp_cd: SpiritCooldownTracker,
             my_char_id: int, opp_char_id: int):
    """把15维写入out[base..base+14] — 迁移窗接线点(build尾部一行)。"""
    o = base
    out[o] = min(1.0, (left.get('airDashCount', 0) or 0) / 3.0); o += 1
    out[o] = min(1.0, (right.get('airDashCount', 0) or 0) / 3.0); o += 1
    out[o] = my_cd.value; o += 1
    out[o] = opp_cd.value; o += 1
    out[o] = min(1.0, (left.get('comboLimit', 0) or 0) / 100.0); o += 1
    out[o] = min(1.0, (right.get('comboLimit', 0) or 0) / 100.0); o += 1
    n, mx = skills_summary(left.get('skills'))
    out[o] = n / 4.0; o += 1
    out[o] = mx / 4.0; o += 1
    n, mx = skills_summary(right.get('skills'))
    out[o] = n / 4.0; o += 1
    out[o] = mx / 4.0; o += 1
    out[o] = orb_broken_norm(left.get('maxSpirit', 1000)); o += 1
    out[o] = orb_broken_norm(right.get('maxSpirit', 1000)); o += 1
    out[o] = 1.0 if right.get('action', 0) in (1, 2) else 0.0; o += 1
    out[o] = 1.0 if (right.get('hitStop', 0) or 0) > 0 else 0.0; o += 1
    out[o] = 1.0 if (left.get('healingCharm', 0) or 0) > 0 or (
        right.get('healingCharm', 0) or 0) > 0 else 0.0
    o += 1
    assert o - base == N_DIMS
    return o - base     # =15


N_DIMS = 15
