# -*- coding: utf-8 -*-
"""task-28: DD(回避结界)仅正防态可用 — 掩码门控(实机 93.6% 验证).

env TH123_DD_GUARD_ONLY:
  1(默认) = 结界/空结界 宏仅当 own action ∈ 150-167(正防/防硬直) unmask;
  0       = 旧行为(A/B 回滚).
背景: 帧日志 recent40/char: barrier 宏决策在 guard/stun 44/47 触发(reimu 93.6%),
非防御态 571 次 0 触发 → 宏序列在正防有效; 缺陷=非防态也可被选(执行成 dash/flight 201/205).
本门控只修"可选择性", 不改宏时序/奖励/动作空间.
"""
from __future__ import annotations

import os

DD_GUARD_ONLY = os.environ.get('TH123_DD_GUARD_ONLY', '1') != '0'
DD_PREFIX = ('结界', '空结界')
GUARD_LO, GUARD_HI = 150, 167   # GUARD_ALL_IDS/GUARD_STUN_IDS 覆盖(实机口径)


def is_guard_action(action):
    """own action 是否正防/防硬直态(150-167)。"""
    try:
        a = int(action or 0)
    except (TypeError, ValueError):
        return False
    return GUARD_LO <= a <= GUARD_HI


def is_dd_macro(name):
    """DD(回避结界)宏: 结界1/2/4/6、空结界4/6(按前缀, 未来新增自动覆盖)。"""
    return str(name or '').startswith(DD_PREFIX)


def dd_gate(mask, names, action):
    """非正防态 mask 掉 DD 宏; 正防态/关闭门控时原样返回(不改其它宏)。"""
    if not DD_GUARD_ONLY or is_guard_action(action):
        return mask
    m = mask.copy()
    for i, n in enumerate(names):
        if is_dd_macro(n):
            m[i] = False
    return m


def startup_line():
    return '[dd_gate] %s guard_only=%d guard_ids=%d-%d' % (
        'ON' if DD_GUARD_ONLY else 'OFF', int(DD_GUARD_ONLY),
        GUARD_LO, GUARD_HI)
