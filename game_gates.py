# -*- coding: utf-8 -*-
"""task-28/29/30 统一执行层 mask 层(2026-10-20).

- task-28: DD(回避结界)仅正防硬直 150-157 可用(158/159-166 mask; 实测 158→be 0/8)
- task-29: 地空门控(air/ground 显式分类; 命令技按名/静态表分地空; 受身不受 AIR_GATE)
- task-30: 不可动门控(action-id 硬直集: 50-78/88/89/97/98/100/143/145/150-157;
  倒地只放 受身/起身; 受创只放 受身; 正防放 DD/铜钱/羽衣+防御切换; 158/159-166 全 mask)
- 空 mask → 仅 待机; 配置异常 → 响亮报错(调用方关闭门控回旧行为); env=0 逐位旧行为.

env: TH123_ACT_MASK(总,默认1) TH123_AIR_GATE TH123_IMMOBILE_GATE TH123_DD_GUARD_ONLY
"""
from __future__ import annotations

import os

# ---- task-28 既有接口(保留兼容) ----
DD_GUARD_ONLY = os.environ.get('TH123_DD_GUARD_ONLY', '1') != '0'
DD_PREFIX = ('结界', '空结界')
GUARD_LO, GUARD_HI = 150, 167   # legacy(task-28 旧宽口径; 新层用 GUARD_STUN_LO/HI)


def is_guard_action(action):
    """legacy: own action 正防/防硬直 150-167(task-28 旧口径)."""
    try:
        a = int(action or 0)
    except (TypeError, ValueError):
        return False
    return GUARD_LO <= a <= GUARD_HI


def is_dd_macro(name):
    return str(name or '').startswith(DD_PREFIX)


def dd_gate(mask, names, action):
    """legacy(task-28): 非 150-167 时 mask DD."""
    if not DD_GUARD_ONLY or is_guard_action(action):
        return mask
    m = mask.copy()
    for i, n in enumerate(names):
        if is_dd_macro(n):
            m[i] = False
    return m


# ---- 统一 mask 层(task-28/29/30) ----
ACT_MASK = os.environ.get('TH123_ACT_MASK', '1') != '0'
AIR_GATE = os.environ.get('TH123_AIR_GATE', '1') != '0'
IMMOBILE_GATE = os.environ.get('TH123_IMMOBILE_GATE', '1') != '0'
GUARD_STUN_LO, GUARD_STUN_HI = 150, 157   # 正防硬直(实测 151/152/155/156 有效)
AIR_DEF_STUN = 158                        # 空中防御硬直 → mask
MISGUARD_LO, MISGUARD_HI = 159, 166       # 错防 → 全 mask

AIR_NAMES = {'jA', 'j6A', 'j8A', 'j2A', 'j2B', 'jC',
             '空冲', '飞翔', '空翔前', '空翔后', '空冲后', '空防',
             '空结界4', '空结界6', '空tech'}
GROUND_MOVE = {'跳跃', '高跳', '前冲', '后冲', '后跳', '斜上冲', '斜后跳'}
BOTH = {'待机', '前进', '后退', '受身'}
GUARD_MACROS = {'立防', '蹲防', '防', '防反'}
UKEMI = {'受身'}
WAKE = {'起身', '起身穿'}
CARDS_GROUND = {'卡·铜钱', '卡·白楼剑'}
GROUND_ATK = {'5A', '2A', '6A', '3A', 'AA', '2B', '5B', '6B', '2C', '5C', 'DA'}
DOWN_ACTS = {88, 89, 97, 98, 100, 143, 145}
HIT_ACTS = set(range(50, 79))


def _is_air(n):
    return n in AIR_NAMES or str(n).startswith('j') or (
        is_dd_macro(n) and '空' in str(n))


def _is_ground_only(n):
    if n in BOTH or n in AIR_NAMES or _is_air(n):
        return False
    return (n in GUARD_MACROS or n in GROUND_ATK or n in GROUND_MOVE
            or n in WAKE or n in CARDS_GROUND
            or (is_dd_macro(n) and '空' not in str(n)))


def apply_state_gates(mask, names, left):
    """统一 mask 层; env=0 时原样返回(逐位旧行为)。"""
    if not ACT_MASK:
        return mask
    act = int(left.get('action', 0) or 0)
    air = bool(left.get('airBorne'))
    m = mask.copy()
    # (a) 地空门控(受身不归 AIR_GATE; 由不可动白名单控制)
    if AIR_GATE:
        for i, n in enumerate(names):
            if not air and _is_air(n):
                m[i] = False
            elif air and _is_ground_only(n):
                m[i] = False
    # (b) 不可动门控(action-id 集合; 不裸用 raw untech)
    if IMMOBILE_GATE:
        allow = None
        if act in DOWN_ACTS:
            allow = UKEMI | WAKE
        elif act in HIT_ACTS:
            allow = set(UKEMI)
        elif GUARD_STUN_LO <= act <= GUARD_STUN_HI:
            allow = set(GUARD_MACROS) | set(CARDS_GROUND) | {
                n for n in names if is_dd_macro(n)}
        elif act == AIR_DEF_STUN or MISGUARD_LO <= act <= MISGUARD_HI:
            allow = set()
        if allow is not None:
            for i, n in enumerate(names):
                if n not in allow:
                    m[i] = False
    # (c) DD 正防门控(150-157; 158/159-166 已由上一条全 mask)
    if DD_GUARD_ONLY and not (GUARD_STUN_LO <= act <= GUARD_STUN_HI):
        for i, n in enumerate(names):
            if is_dd_macro(n):
                m[i] = False
    # (d) 空 mask → 仅 待机; 无待机宏 → 响亮报错(调用方关 gate 回旧行为)
    if not m.any():
        idle = [i for i, n in enumerate(names) if n == '待机']
        if not idle:
            raise RuntimeError(
                '[act_mask] gate 后 mask 全空且无"待机"宏 — 配置异常; '
                '请设 TH123_ACT_MASK=0 回旧行为并上报')
        m[:] = False
        m[idle[0]] = True
    return m


def startup_line():
    return ('[act_mask] %s air=%d immobile=%d dd_guard=%d guard_ids=%d-%d '
            '(158/159-166 masked)' % (
                'ON' if ACT_MASK else 'OFF', int(AIR_GATE),
                int(IMMOBILE_GATE), int(DD_GUARD_ONLY), GUARD_STUN_LO,
                GUARD_STUN_HI))
