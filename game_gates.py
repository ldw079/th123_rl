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

import numpy as np

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
# task-39/41/44: 运行时埋点(每次 apply_state_gates 计一次)
_GATE_DECISIONS = 0
_MASKED_DECISIONS = 0
_CHOICE_DECISIONS = 0
_CHOICE_MASKED = 0
_PREF_DECISIONS = 0
_PREF_REMOVED = 0
_PREF_MASS_SUM = 0.0
_PREF_MASS_N = 0
_LAST_REMOVED = frozenset()
_REMOVED_TOTAL = 0
_ALLOWED_SUM = 0
_ALLOWED_N = 0
_ALLOWED_MIN = 10 ** 9


def reset_masked_stats():
    global _GATE_DECISIONS, _MASKED_DECISIONS
    global _CHOICE_DECISIONS, _CHOICE_MASKED
    global _PREF_DECISIONS, _PREF_REMOVED, _PREF_MASS_SUM, _PREF_MASS_N
    global _LAST_REMOVED, _REMOVED_TOTAL
    _GATE_DECISIONS = 0
    _MASKED_DECISIONS = 0
    _CHOICE_DECISIONS = 0
    _CHOICE_MASKED = 0
    _PREF_DECISIONS = 0
    _PREF_REMOVED = 0
    _PREF_MASS_SUM = 0.0
    _PREF_MASS_N = 0
    _LAST_REMOVED = frozenset()
    _REMOVED_TOTAL = 0
    global _ALLOWED_SUM, _ALLOWED_N, _ALLOWED_MIN
    _ALLOWED_SUM = 0
    _ALLOWED_N = 0
    _ALLOWED_MIN = 10 ** 9


def gate_metrics_line():
    n, m = _GATE_DECISIONS, _MASKED_DECISIONS
    pct = (100.0 * m / n) if n else 0.0
    avg = (_ALLOWED_SUM / _ALLOWED_N) if _ALLOWED_N else 0.0
    mn = _ALLOWED_MIN if _ALLOWED_N else 0
    return ('[act_mask] gate_changed=%d/%d (%.1f%%) '
            'allowed_avg=%.1f allowed_min=%d' % (
                m, n, pct, avg, mn))


def masked_line():
    n, m = _GATE_DECISIONS, _MASKED_DECISIONS
    pct = (100.0 * m / n) if n else 0.0
    return '[act_mask] masked=%d/%d (%.1f%%)' % (m, n, pct)


def note_choice(idx):
    """采样后调用: 记录选中项是否在 gate 移除集合(应恒 False)."""
    global _CHOICE_DECISIONS, _CHOICE_MASKED
    _CHOICE_DECISIONS += 1
    if int(idx) in _LAST_REMOVED:
        _CHOICE_MASKED += 1
        return False
    return True


def choice_legal(idx):
    return int(idx) not in _LAST_REMOVED


def note_pref(raw_probs):
    """task-44修: raw softmax 在 gate 移除集合上的概率质量 + raw top1 频次.

    raw_probs = gate 前(mask=None/bias=None) softmax 分布; 移除集合=_LAST_REMOVED.
    """
    global _PREF_DECISIONS, _PREF_REMOVED, _PREF_MASS_SUM, _PREF_MASS_N
    import numpy as np
    probs = np.asarray(raw_probs, dtype=np.float64).ravel()
    _PREF_DECISIONS += 1
    if _LAST_REMOVED:
        _PREF_MASS_SUM += float(sum(probs[i] for i in _LAST_REMOVED))
        _PREF_MASS_N += 1
    top1 = int(np.argmax(probs))
    if top1 in _LAST_REMOVED:
        _PREF_REMOVED += 1
        return False
    return True


def pref_on_removed_line():
    n, m = _PREF_DECISIONS, _PREF_REMOVED
    mass_pct = (100.0 * _PREF_MASS_SUM / _PREF_MASS_N) if _PREF_MASS_N else 0.0
    return ('[act_mask] pref_removed_mass=%.3f%% pref_removed_top1=%d/%d'
            % (mass_pct, m, n))


def masked_choice_line():
    nc, mc = _CHOICE_DECISIONS, _CHOICE_MASKED
    pct = (100.0 * mc / nc) if nc else 0.0
    n, m = _GATE_DECISIONS, _MASKED_DECISIONS
    removed_pct = (100.0 * m / n) if n else 0.0
    return ('[act_mask] masked_choice=%d/%d (%.1f%%) %s gate_removed=%d/%d '
            '(%.1f%%)' % (mc, nc, pct, pref_on_removed_line().replace(
                '[act_mask] ', ''), m, n, removed_pct))
ACT_MASK = os.environ.get('TH123_ACT_MASK', '1') != '0'
# task-29/30 阶段1: 缓冲原语开关(默认0=旧行为; =1 时 stun 帧白名单加 buf 槽)
BUFFER = os.environ.get('TH123_BUFFER', '0') != '0'
BUFFER_NAMES = tuple(n for n in os.environ.get(
    'TH123_BUFFER_NAMES', '跳跃,5A').split(',') if n)
# task-34 2a: 受身方向令牌(前冲/后冲 仅 stun 帧作方向选择)
BUFFER_UKEMI_DIR = os.environ.get('TH123_BUFFER_UKEMI_DIR', '0') != '0'
UKEMI_DIR_TOKENS = ('前冲', '后冲')
# task-32 stage1: 防御取消(probe: 防御硬直末 A → 动作330) — 防御帧白名单并集近战宏
GUARD_CANCEL = os.environ.get('TH123_GUARD_CANCEL', '0') != '0'
GUARD_CANCEL_NAMES = ('5A', '2A', '6A', '3A', '4A', 'DA')
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
# task-39: 指令技静态地空表 — 数字方向开头(623/236/214/22/46/41236/63214...)为地面
# 指令技(空中变体由 j* 前缀/空* 命名单独归类); 供地空门控使用.
CMD_GROUND = set()      # 显式补充(若发现某数字名字实为空中技, 记录于此并翻转分类)
CMD_GROUND_PREFIX = ('236', '623', '214', '22', '46', '41236', '63214',
                     '236236', '214214', '623623')
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


def _is_cmd_ground(n):
    """指令技静态表: 数字方向开头且非 j/空 → 地面指令技(task-39)."""
    s = str(n)
    if not s or s[0] not in '0123456789':
        return False
    return any(s.startswith(p) for p in CMD_GROUND_PREFIX) or s in CMD_GROUND


def _is_ground_only(n):
    if n in BOTH or n in AIR_NAMES or _is_air(n):
        return False
    return (n in GUARD_MACROS or n in GROUND_ATK or n in GROUND_MOVE
            or n in WAKE or n in CARDS_GROUND or _is_cmd_ground(n)
            or (is_dd_macro(n) and '空' not in str(n)))


def apply_state_gates(mask, names, left, buf_block=False):
    """统一 mask 层; env=0 时原样返回(逐位旧行为).

    buf_block=True(task-56): 本段已登记过/pending 存在 → 屏蔽
    方向令牌/受身/跳跃/5A(决策正常进 PPO, 不再吞).
    """
    if not ACT_MASK:
        return mask
    globals()['_GATE_DECISIONS'] = _GATE_DECISIONS + 1
    _orig = mask
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
        _buf_ok = BUFFER
        if act in DOWN_ACTS:
            allow = UKEMI | WAKE
        elif act in HIT_ACTS:
            allow = set(UKEMI)
            if _buf_ok and not buf_block:
                allow = allow | set(BUFFER_NAMES)
            if BUFFER_UKEMI_DIR and not buf_block:
                allow = allow | set(UKEMI_DIR_TOKENS)
            if buf_block:
                allow = set()   # 只剩待机(方向/受身/跳跃/5A 全屏蔽)
            if GUARD_CANCEL:
                allow = allow | set(GUARD_CANCEL_NAMES)
        elif GUARD_STUN_LO <= act <= GUARD_STUN_HI:
            allow = set(GUARD_MACROS) | set(CARDS_GROUND) | {
                n for n in names if is_dd_macro(n)}
            if _buf_ok and not buf_block:
                allow = allow | set(BUFFER_NAMES)
        elif act == AIR_DEF_STUN or MISGUARD_LO <= act <= MISGUARD_HI:
            allow = (set(BUFFER_NAMES) if (_buf_ok and not buf_block)
                     else set())
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
    _rem = np.nonzero(np.asarray(_orig) & ~np.asarray(m))[0]
    globals()['_LAST_REMOVED'] = frozenset(int(x) for x in _rem)
    globals()['_REMOVED_TOTAL'] = _REMOVED_TOTAL + len(_rem)
    if not (m == _orig).all():
        globals()['_MASKED_DECISIONS'] = _MASKED_DECISIONS + 1
    _n_allow = int(np.count_nonzero(m))
    globals()['_ALLOWED_SUM'] = _ALLOWED_SUM + _n_allow
    globals()['_ALLOWED_N'] = _ALLOWED_N + 1
    if _n_allow < _ALLOWED_MIN:
        globals()['_ALLOWED_MIN'] = _n_allow
    return m


def startup_line():
    return ('[act_mask] %s air=%d immobile=%d dd_guard=%d guard_ids=%d-%d '
            '(158/159-166 masked) buffer=%d K=%d maxwait=%d guard_cancel=%d'
            % ('ON' if ACT_MASK else 'OFF', int(AIR_GATE),
               int(IMMOBILE_GATE), int(DD_GUARD_ONLY), GUARD_STUN_LO,
               GUARD_STUN_HI, int(BUFFER),
               int(os.environ.get('TH123_BUFFER_K', '6')),
               int(os.environ.get('TH123_BUFFER_MAXWAIT', '0')) or -1,
               int(GUARD_CANCEL)))
