# -*- coding: utf-8 -*-
"""②等级条件宏: 根据当前技能等级动态调整连段宏的取消时序。
原理: 技能卡升级后必杀发生帧变快 → 取消窗口提前开 → 尾段预置帧可减。
用法: 在宏执行前调用 adjust_script(script, skill_levels) 获取调整后的脚本。"""

# 每级减少的帧数(经验估计: Lv2减2帧, Lv3减4帧)
LEVEL_CANCEL_REDUCTION = {0: 0, 1: 2, 2: 4}

# 各技能槽对应的取消指令前缀(用于识别尾段中的取消步)
# 槽0=236系, 槽1=623系, 槽2=214系, 槽3=22系
SLOT_DIRECTION_PATTERNS = {
    0: ('down', 'down-right', 'right'),      # 236: ↓↘→
    1: ('right', 'down', 'down-right'),       # 623: →↓↘
    2: ('left', 'down-left', 'left'),          # 214: ←↙←
    3: ('down', 'down'),                        # 22: ↓↓
}


def adjust_script(script, skill_levels):
    """根据技能等级调整宏脚本的尾段帧数。
    script: [(keys, frames), ...] 原始宏脚本
    skill_levels: [lv_236, lv_623, lv_214, lv_22] 各0-2
    返回: 调整后的脚本(浅拷贝, 不修改原脚本)
    """
    if not any(lv > 0 for lv in skill_levels):
        return script  # 全Lv1, 不需要调整

    adjusted = list(script)
    # 找confirm门后面的取消步(方向预置帧), 按对应技能等级缩减
    in_post_confirm = False
    for i, (keys, fr) in enumerate(adjusted):
        if isinstance(keys, str):
            if keys == 'confirm':
                in_post_confirm = True
            continue
        if in_post_confirm and isinstance(keys, tuple) and len(keys) > 0:
            # 检查这一步是哪个技能槽的方向预置
            slot = _match_slot(keys)
            if slot is not None and skill_levels[slot] > 0:
                reduction = LEVEL_CANCEL_REDUCTION[skill_levels[slot]]
                if reduction > 0 and fr > reduction:
                    adjusted[i] = (keys, fr - reduction)
    return adjusted


def _match_slot(keys):
    """从取消步按键推断技能槽。
    R39(第十轮§4-5): 原`{'down'}/{'down','right'}前哨return None`把
    236/22的取消步全判死(且623/214只匹配到方向预置步而非取消步,
    缩预置帧会破坏指令缓冲)。改按**按钮+末方向**识别取消步:
    236=(→)+B/C, 623=(↓↘)+B/C, 214=(←或↙)+B/C, 22=(↓)+B/C。"""
    ks = set(keys)
    if not (ks & {'B', 'C'}):
        return None    # 纯方向预置步不调
    dirs = ks - {'B', 'C'}
    if dirs == {'right'}:
        return 0       # 236
    if dirs == {'down', 'right'}:
        return 1       # 623
    if dirs in ({'left'}, {'down', 'left'}):
        return 2       # 214
    if dirs == {'down'}:
        return 3       # 22
    return None
