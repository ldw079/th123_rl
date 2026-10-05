# -*- coding: utf-8 -*-
"""技能卡ID→技能槽映射。
**R4注记(R32审查2026-10-02)**: 来源为"CHM攻略卡表"(文件头旧注),
攻略是外部资料而非测量 — 槽位映射未经hitlab二次标定。
各角色100-110区间三表槽位一致(结构对称性佐证), 但个别招的
槽位归属仍可能有误(如萃香110的归属)。使用时以此为先验,
生产验证后再升级为实测。
每个角色4个技能槽对应不同输入指令, 技能卡使用后永久升级该槽。
槽位编码: 0=236系, 1=623系, 2=214系, 3=22系
等级编码: 0=Lv1(默认), 1=Lv2, 2=Lv3(需两张同名卡)"""

# 灵梦
# R39(第十轮§4-4): 修三处经宏库注释锚定的错位(102亜空穴=22系,
# 原映射236)。111(雨乞祈り)三角色均未映射 — 家族归属未标定,
# 空映射优于错映射(R4), 待hitlab实测后补。
SKILL_MAP_REIMU = {
    100: 0, 101: 0,            # 236系: 封魔针/空中封魔针
    102: 3,                    # 22系: 亜空穴(原误映射236 — R39修)
    103: 1, 104: 1, 105: 1,    # 623系: 昇天脚/低速升天脚/急速升天脚
    106: 2, 107: 2,            # 214系: 幻想空/常置幻想空
    108: 3, 109: 3,            # 22系: 鬼神玉/即妙神
}

# 魔理沙
SKILL_MAP_MARISA = {
    100: 0, 101: 0, 102: 0,    # 236系: 星光弹/高密度/低密度
    103: 1, 104: 1, 105: 1,    # 623系: 升天撞/上升扫/宽域
    106: 3, 107: 2,            # 106デビルダムトーチ=22系(原误映射214 — R39修); 107窄域=214
    108: 3, 109: 3, 110: 3,    # 22系: 地火/大火/小火
}

# 萃香
SKILL_MAP_SUIKA = {
    100: 0, 101: 0, 102: 0,    # 236系: 醉酒雾/浓雾/毒雾
    103: 1, 104: 1, 105: 1,    # 623系: 萃鬼投/快速/威力
    106: 2, 107: 2,            # 214系: 雾散/集中
    108: 2, 109: 3, 110: 3,    # 108踏鞴=214系(macros_suika注释锚定, 原误映射22 — R39修); 109/110=22系
}

CHAR_SKILL_MAPS = {
    'reimu': SKILL_MAP_REIMU,
    'marisa': SKILL_MAP_MARISA,
    'suika': SKILL_MAP_SUIKA,
    # R44(2026-10-04): 六新角色技能槽位映射 — R4纪律: 空映射优于错映射
    # (槽位归属未标定, 特征恒0但无害; 待hitlab标定后逐卡补)
    'sakuya': {}, 'patchouli': {}, 'yuyuko': {},
    'reisen': {}, 'komachi': {}, 'tenshi': {},
    # R45: 剩余11角色 — 同R4纪律
    'alice': {}, 'youmu': {}, 'remilia': {}, 'yukari': {},
    'aya': {}, 'iku': {}, 'sanae': {}, 'cirno': {},
    'meiling': {}, 'utsuho': {}, 'suwako': {},
}

N_SKILL_SLOTS = 4  # 236/623/214/22


def skill_levels_from_hand(hand_bytes, prev_levels=None, prev_hand=None,
                           char=None):
    """从手牌数据推导当前技能等级。
    hand_bytes: 包的hand字段(10字节, 5对(id,count))
    prev_levels: 上一帧的等级列表(4元素)
    prev_hand: 上一帧的hand_bytes(检测卡消耗)
    char: 角色名(精确查角色卡表; None=三表合并查 — 100..110区间三表
          槽位一致, 合并无歧义。R19接通: 原cid_to_slot为恒None桩,
          本函数与level_macros双双失效, 审查2026-10-02)
    返回: [lv_236, lv_623, lv_214, lv_22] 各0-2"""
    levels = list(prev_levels) if prev_levels else [0, 0, 0, 0]
    if prev_hand is None:
        return levels

    # 检测技能卡消耗: 上一帧有→这一帧没了→该技能槽等级+1
    prev_ids = set()
    for i in range(5):
        cid = prev_hand[i * 2]
        if cid != 0xFF:
            prev_ids.add(cid)
    cur_ids = set()
    for i in range(5):
        cid = hand_bytes[i * 2]
        if cid != 0xFF:
            cur_ids.add(cid)

    # 在prev有但cur没有的技能卡 → 已消耗
    # 注意: 手牌空间有限, 卡可能被新卡替换而非使用
    # 更可靠的判定: 选中位(hand[0])的count减少了
    # 简化: 用消失检测+count减少的组合
    for cid in (prev_ids - cur_ids):
        if 100 <= cid < 200:
            slot = cid_to_slot(cid, char)
            if slot is not None and levels[slot] < 2:
                levels[slot] += 1

    # 选中卡count减少也视为使用
    if prev_hand[0] != 0xFF and prev_hand[0] == hand_bytes[0]:
        if prev_hand[1] > hand_bytes[1]:
            cid = hand_bytes[0]
            if 100 <= cid < 200:
                slot = cid_to_slot(cid, char)
                if slot is not None and levels[slot] < 2:
                    levels[slot] += 1

    return levels


def cid_to_slot(cid, char=None):
    """卡ID→技能槽。R19(审查2026-10-02): 原为无条件returnNone的桩。
    R61f(F3, 从零审计): **合并路径(char=None)已删** — 原docstring称
    "100..110区间三表槽位一致无歧义"为假: cid102(reimu=22系3/
    marisa·suika=236系0)/cid106(marisa=3,其他=2)/cid108(suika=2,
    其他=3)三处分歧, 合并查表按dict序取reimu — 跨角色手牌解析错槽。
    现char=None一律返回None(响亮于错表); 生产两处调用均传char ✓;
    表来源: 文件头CHM攻略卡表(R4注记: 未经hitlab二次标定)。"""
    if not (100 <= cid < 200) or char is None:
        return None
    return CHAR_SKILL_MAPS.get(char, {}).get(cid)


def hand_skill_availability(hand_bytes, char):
    """手牌中各技能槽的升级卡可用性(不依赖消耗检测).
    返回: [avail_236, avail_623, avail_214, avail_22] 各0-1"""
    smap = CHAR_SKILL_MAPS.get(char, {})
    avail = [0.0] * N_SKILL_SLOTS
    for i in range(5):
        cid = hand_bytes[i * 2]
        if cid != 0xFF and cid in smap:
            slot = smap[cid]
            avail[slot] = min(1.0, avail[slot] + 0.5)  # 每张+0.5, 2张满
    return avail
