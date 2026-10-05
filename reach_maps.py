# -*- coding: utf-8 -*-
"""宏→攻击射程解析(R24-29)。
R29(用户2026-10-02落实): **显式move ID表**替换脚本签名推导 —
输入→招式映射是状态依赖的(受身与4A同签名left+A), 签名推导无法
区分状态依赖招; 显式表按宏名手写, ID全部来自SokuLib引擎枚举
(docs/soku_action_ids.md, Action.hpp@09fed348)。
表外宏一律无射程(不门控不特征) — 新增攻击宏时须在此登记。
数据链: 宏名→(move ids...)→XML hitbox射程(action_tables.REACH/_V)。
f变体(301=f5A/311=f2A)与近版取max; 连段/确认系宏按其首攻击步
所属招登记。

**设计决策(审查2026-10-02确认)**: B/C系弹幕宏不参与射程门控
(发射框≠弹幕射程, 弹速×飞行时间才是 — 待弹型行为画像层)。
这意味着侧向量的射程差特征块在弹幕宏上恒为0 — 0的含义是
"无射程信息"而非"正好在射程内"。这是有意为之, 非漏登记。"""
import os

import numpy as np

from action_tables import CHAR_ACTION_TABLES

# ---- 显式映射表(SokuLib枚举; 元组=取max的id集) ----
# 通用体术(三角色引擎级一致):
_COMMON = {
    '5A': (300, 301), '5A确认': (300, 301),
    '2A': (303, 311), '2A确认': (303, 311),
    '6A': (302,), 'DA': (305, 302),          # DA=66A冲刺A(305),退6A
    '3A': (304,), '4A': (330,),
    'jA': (306,), 'j6A': (307,), 'j2A': (308,), 'j8A': (309,),
    '连段A': (300, 301, 320, 321),           # 5A起手+连段后续段(320s)
    '连段B': (300, 301, 320, 321, 322),
    '连段C': (300, 301, 320, 321, 322, 323),
    '版边连A': (300, 301, 320, 321, 322),
    '空连A': (306, 325,),                    # j5A起手+j5AA(325)
    '压制A': (303, 311, 62),                 # 2A起手(压制系首步=蹲A)
    '压制B': (307,),                         # 跳入j6A起手
    # R39(第十轮§4-7): 原子宏+TM宏登记(文件头自订规则"新增攻击宏须
    # 登记"对R31/R35新宏未执行 — R35重心恰是原子宏)
    '原子·确认5A': (300, 301),
    '原子·地面链': (300, 301, 320, 321),
    '原子·空链': (306, 308),                 # hj9跳入jA→j2A
    '原子·收尾': (308,),                     # 空翔前dash→j2A收尾
    'TM·2a连': (303, 311),
    'TM·4a连': (330,),
    'TM·6a终结': (302,),
    'TM·空连终结': (306,),
    'TM·对空连': (308,),
    # R44(六新角色): 通用宏直接复用_COMMON映射(_COMMON即引擎级通用表)
    # 注: 必杀宏(236B/623B/22B/214B/C系)与TM·必杀SC连**不登记射程** —
    # 5xx动作ID↔指令映射未经hitlab标定, XML表内多个5xx候选无从裁决,
    # 登记错射程会污染距离门控(空映射=不门控, 优于错映射, R4纪律)。
}
CHAR_MACRO_MOVES = {
    'reimu': dict(_COMMON),
    'marisa': dict(_COMMON, **{'B6C连': (400, 408)}),   # B起手+66B
    'suika': dict(_COMMON),
    # R44(2026-10-04): 六新角色 — 通用骨架表(生成器tools/gen_newchar_libs.py)
    'sakuya': dict(_COMMON),
    'patchouli': dict(_COMMON),
    'yuyuko': dict(_COMMON, **{'TM·2a_6a_6c_dskill4b': (303,), 'TM·5a_5aa_5aaa_sc203_': (300,), 'TM·hj9_j2a_2a_2b_6c_h': (303,), 'TM·5a_5aa_5aaa_f5a_6a': (300,)}),
    'reisen': dict(_COMMON),
    'komachi': dict(_COMMON, **{'TM·5a_5aa_5aaa_5aaaa_': (300,), 'TM·f5a_6c_sc206': (300,), 'TM·f5a_6c_sc206': (300,), 'TM·hj8_j66_j2a_sc203': (305,)}),
    'tenshi': dict(_COMMON, **{'TM·hj9_j5a_j2c_jsc207': (300,), 'TM·6_d6_5a_5aa_2b_sc2': (300,), 'TM·d6_5a_5aa_2b_5c_d6': (300,), 'TM·6_6b_hj9_j5a_j2b_5': (401,)}),
    # R45: 剩余11角色 — 全20角色齐备
    'alice': dict(_COMMON, **{'TM·8_j6a': (302,), 'TM·8_j6a_j6a_6a': (302,), 'TM·d236b_sc200_sc203': (400,), 'TM·2a_3a_dskill1b_hj9': (303,)}),
    'youmu': dict(_COMMON, **{'TM·hj8_j2a_4_sc204': (303,), 'TM·f2a_sc203': (303,), 'TM·d623c_sc203': (400,), 'TM·d6_2c_hj8_j2a_sc20': (412,)}),
    'remilia': dict(_COMMON, **{'TM·5a_5aa_5aaa_5aaaa_': (300,), 'TM·5a_5aa_5aaa_5aaaa_': (300,), 'TM·2a_sc206': (303,), 'TM·5a_5aa_5aaa_5aaaa_': (300,)}),
    'yukari': dict(_COMMON, **{'TM·3a_sc215': (304,), 'TM·3a_sc208': (304,), 'TM·5a_5aa_5aaa_sc201_': (300,), 'TM·5a_5aa_5aaa_5aaaa_': (300,)}),
    'aya': dict(_COMMON, **{'TM·6_d236b_sc206': (400,), 'TM·2a_2a_sc206': (303,), 'TM·hj9_j5a_j5b_j66_j5': (300,)}),
    'iku': dict(_COMMON),
    'sanae': dict(_COMMON, **{'TM·2a_3a_2c_sc205': (303,), 'TM·5a_5aa_5aaa_5aaaa_': (300,), 'TM·2a_3a_5c_sc205': (303,), 'TM·5a_5aa_5aaa_2b_sc2': (300,)}),
    'cirno': dict(_COMMON, **{'TM·5a_5aa_5aaa_5c_sc2': (300,), 'TM·5a_5aa_5aaa_5c_d62': (300,), 'TM·hj9_j5a_j6a_j5c_j6': (300,), 'TM·hj9_j5a_j5c_j66_j5': (300,)}),
    'meiling': dict(_COMMON, **{'TM·d6_5a_5aa_5aaa_d62': (300,), 'TM·5a_5aa_5aaa_2b_5c_': (300,), 'TM·f5a_3a_6c_d623c': (300,)}),
    'utsuho': dict(_COMMON),
    'suwako': dict(_COMMON, **{'TM·8_j8a_sc208': (309,), 'TM·f5a_sc208': (300,), 'TM·5a_5aa_5aaa_j5b_j6': (300,), 'TM·5a_5aa_5aaa_5aaaa': (300,)}),
}
REACH_MARGIN = 80.0   # 掩码放宽(起手期间对手位移+模型前冲余量)

# R40(第十一轮§6-6): 显式"不可测"登记 — 区分"未登记(疏漏)"与
# "无判定数据(有意不登记)"。必杀系5xx↔指令映射未经hitlab标定(见上注)。
UNMEASURABLE = {
    '236B', '236C', '623B', '623C', '22B', '22C', '214B', '214C',
    'TM·必杀SC连',
}
# R44: 六新角色的必杀宏同规则(引擎5xx↔指令映射待hitlab标定)

# R30(用户2026-10-02"精密时序"): 各招发生帧(枚举语义+XML hitbox首帧
# 近似+Trialmode expected帧偏移交叉校准)。用于untech差值特征:
# "我现在出这招, 对手untech还够不够?" = untech - startup_i
MOVE_STARTUP = {
    300: 6, 301: 8, 302: 14, 303: 10, 304: 25, 305: 12, 330: 14,
    306: 8, 307: 12, 308: 12, 309: 12,
    320: 8, 321: 8, 322: 10, 323: 10, 325: 10,
    400: 17, 402: 17, 410: 22, 412: 22,
    500: 15,  # 必杀近似(逐技能标定待hitlab)
}


def resolve_startup(macros, char):
    """[(name, script), ...] → 发生帧数组(N,)(0=未知)。
    取该宏登记ID集中最小startup(最先够得着的那招)。"""
    moves = CHAR_MACRO_MOVES.get(char, {})
    out = np.zeros(len(macros), dtype=np.float32)
    for i, (name, _s) in enumerate(macros):
        mids = moves.get(name)
        if not mids:
            continue
        sts = [MOVE_STARTUP[m] for m in mids if m in MOVE_STARTUP]
        if sts:
            out[i] = float(min(sts))
    return out


def resolve_reach(macros, char):
    """[(name, script), ...] → (横向, 纵向)射程数组(N,)。
    R29: 查显式表 — 表外宏=无射程。"""
    tab = CHAR_ACTION_TABLES.get(char, {})
    reach_tab = tab.get('reach', {})
    reach_v_tab = tab.get('reach_v', {})
    moves = CHAR_MACRO_MOVES.get(char, {})
    out_x = np.zeros(len(macros), dtype=np.float32)
    out_y = np.zeros(len(macros), dtype=np.float32)
    for i, (name, _script) in enumerate(macros):
        mids = moves.get(name)
        if not mids:
            continue
        xs = [reach_tab[m] for m in mids if m in reach_tab]
        ys = [reach_v_tab[m] for m in mids if m in reach_v_tab]
        if xs:
            out_x[i] = float(max(xs))
        if ys:
            out_y[i] = float(max(ys))
    return out_x, out_y
