# -*- coding: utf-8 -*-
"""技能装备追踪器: 软件推断当前各槽位装备的必杀技变体。

原理: 技能卡(ID 100~111)使用后替换对应槽位的必杀技。
追踪自身手卡的消费事件 → 更新槽位状态 → 侧输入 + pmask门控。

槽位映射(th123通用):
  236槽: 技能卡 100~105 → 236B/C变为对应技能
  623槽: 技能卡 106~108 → 623B/C变为对应技能
  22槽 : 技能卡 109~111 → 22B/C变为对应技能
  (214槽: 部分角色有第四槽)

无内存偏移依赖: 纯软件推断, 从手卡消费事件驱动。
校准: 通过动作ID反馈验证(236B出招后sensor读到不同ID→推断正确)。
"""
from card_tables import CHAR_CARD_TABLES, SYSTEM_CARDS


# 槽位定义: 每角色独立标定(不能按ID范围简单划分!)
# 灵梦(0): 236=[100,104,108] 623=[102,103,106,107,110] 22=[101,105,109,111]
# 魔理沙(1): 236=[100,103,107] 623=[102,106,110] 22=[101,105,109]
# 其他角色: 需查攻略wiki标定(暂用粗分组, 标记TODO)
_SLOT_OVERRIDES = {
    0: {"236": [100, 104, 108],
        "623": [102, 103, 106, 107, 110],
        "22":  [101, 105, 109, 111]},
    1: {"236": [100, 103, 107],
        "623": [102, 106, 110],
        "22":  [101, 105, 109]},
}


# 每角色的技能卡→槽位映射(优先用标定表, 否则按ID范围粗分)
def _build_slot_map(char_id):
    """角色ID → {槽名: [卡ID列表]}"""
    if char_id in _SLOT_OVERRIDES:
        return {k: list(v) for k, v in _SLOT_OVERRIDES[char_id].items()}
    # TODO: 其他角色需查攻略wiki标定, 当前按ID范围粗分(可能不准)
    cards = CHAR_CARD_TABLES.get(char_id, [])
    result = {"236": [], "623": [], "22": []}
    for cid, name, _cost in cards:
        if 100 <= cid < 112:
            if cid <= 105:
                result["236"].append(cid)
            elif cid <= 108:
                result["623"].append(cid)
            elif cid <= 111:
                result["22"].append(cid)
    return result


class SkillLoadout:
    """追踪当前装备: 每槽 {skill_card_id, level, is_default}。"""

    def __init__(self, char_id=0):
        self.char_id = char_id
        self.slot_map = _build_slot_map(char_id)
        self.slots = {
            "236": {"card_id": None, "level": 0, "is_default": True},
            "623": {"card_id": None, "level": 0, "is_default": True},
            "22":  {"card_id": None, "level": 0, "is_default": True},
        }

    def reset(self):
        """新对局: 槽位回到默认。"""
        for s in self.slots.values():
            s["card_id"] = None
            s["level"] = 0
            s["is_default"] = True

    def on_card_consumed(self, card_id, card_level):
        """sc_tick消费手卡时调用: 技能卡→更新对应槽位。"""
        if not (100 <= card_id < 112):
            return
        for slot_name, ids in self.slot_map.items():
            if card_id in ids:
                self.slots[slot_name] = {
                    "card_id": card_id,
                    "level": card_level or 1,
                    "is_default": False,
                }
                return

    def features(self):
        """6维侧输入: 每槽 (is_changed, level/4)。"""
        out = []
        for name in ("236", "623", "22"):
            s = self.slots[name]
            out.append(0.0 if s["is_default"] else 1.0)
            out.append(min(1.0, (s["level"] or 0) / 4.0))
        return out   # 6维: [236_changed, 236_lv, 623_changed, 623_lv, 22_changed, 22_lv]

    def has_skill(self, slot, card_id=None):
        """查询槽位: 指定card_id或任一非默认。"""
        s = self.slots[slot]
        if card_id is None:
            return not s["is_default"]
        return s["card_id"] == card_id

    def summary(self):
        parts = []
        for name in ("236", "623", "22"):
            s = self.slots[name]
            if not s["is_default"]:
                parts.append("%s=%d(L%d)" % (name, s["card_id"], s["level"]))
        return "装备[" + (" ".join(parts) if parts else "全默认") + "]"
