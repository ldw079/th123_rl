# -*- coding: utf-8 -*-
"""task-20 Phase1 进攻类奖励: R-a 惩罚窗命中结算 + R-e 窗口攻击 bias + R-d 空挥再平衡.

env(全部可关; 默认见下):
  TH123_REW_ATK=1              总开关
  TH123_REW_ATK_PUNISH=0.10    窗口内起手并命中 → 加成(成功才结算)
  TH123_REW_ATK_WINDOW=60      对手出招后恢复窗长度(F)
  TH123_REW_ATK_CONFIRM=30     起手后命中确认窗(F)
  TH123_REW_ATK_DX_MAX=350     仅近/中距窗口起手计
  TH123_REW_ATK_BIAS=0.2       R-e 窗口内攻击宏 logit bias(破冷启动; 进入 stored_logp)
  TH123_REW_ATK_BIAS_DECAY=800 bias 线性衰减 updates(≈35h)
  TH123_REW_ATK_BIAS_HOURS=0   >0 时按墙上小时衰减(24h→0, 优先)
  TH123_REW_ATK_WHIFF_NEAR=1.2 非窗口近距空挥 ×(窗口内不加重=1.0)
  TH123_REW_ATK_WHIFF_FAR=0.5  远距射击空挥 ×
  TH123_REW_ATK_WHIFF_MELEE_FAR=1.2 远距近战空挥 ×
窗口定义: 对手 300-598(出招启动) 结束后的 WINDOW 帧内 / 对手 untech>0 / 对手 guardstun(150-158)。
"""
from __future__ import annotations

import os
import time

REW_ATK = os.environ.get('TH123_REW_ATK', '1') != '0'
R_PUNISH = float(os.environ.get('TH123_REW_ATK_PUNISH', '0.10'))
WINDOW = int(os.environ.get('TH123_REW_ATK_WINDOW', '60'))
CONFIRM = int(os.environ.get('TH123_REW_ATK_CONFIRM', '30'))
DX_MAX = float(os.environ.get('TH123_REW_ATK_DX_MAX', '350'))
BIAS = float(os.environ.get('TH123_REW_ATK_BIAS', '0.2'))
BIAS_DECAY = int(os.environ.get('TH123_REW_ATK_BIAS_DECAY', '800'))
BIAS_HOURS = float(os.environ.get('TH123_REW_ATK_BIAS_HOURS', '0'))
WHIFF_NEAR = float(os.environ.get('TH123_REW_ATK_WHIFF_NEAR', '1.2'))
WHIFF_FAR = float(os.environ.get('TH123_REW_ATK_WHIFF_FAR', '0.5'))
WHIFF_MELEE_FAR = float(os.environ.get('TH123_REW_ATK_WHIFF_MELEE_FAR', '1.2'))

ATTACK_CLS = ('MELEE', 'BULLET', 'SKILL')


def attack_macro(name, classify):
    """是否攻击类宏(classify 由 my_punish_tracker.classify 提供)。"""
    try:
        return classify(name or '', None) in ATTACK_CLS if classify else False
    except Exception:
        return False


def reset_state(self):
    self._atk = {
        't': 0,
        'last_startup': None,     # 对手最近一次出招启动结束时刻
        'in_window': False,
        'pending': None,          # {'t':.., 'dx':..}
        'attempts': 0, 'hits': 0, 'whiffs': 0,
        'bonus': 0.0,
        't0': time.time(),
        'u0': None,               # bias 衰减起点 updates(首次调用记录)
    }


def _state(self):
    st = getattr(self, '_atk', None)
    if st is None:
        reset_state(self)
        st = self._atk
    return st


def window_active(right, st, t):
    """更新惩罚窗状态; 返回当前是否在窗口内。

    right: dict(action/untech); st: 状态; t: 帧计数。
    """
    act = int(right.get('action', 0) or 0)
    unt = int(right.get('untech', 0) or 0)
    in_startup = 300 <= act <= 598
    guardstun = 150 <= act <= 158
    if in_startup:
        st['last_startup'] = t
        st['in_window'] = True
        return True
    if unt > 0 or guardstun:
        st['in_window'] = True
        return True
    ls = st.get('last_startup')
    if ls is not None and 0 <= (t - ls) <= WINDOW:
        st['in_window'] = True
        return True
    st['in_window'] = False
    return False


def step(self, left, right, d_take, d_deal, t):
    """逐帧: 窗口跟踪 + pending 命中结算(成功才结算). 返回本帧奖励。"""
    if not REW_ATK:
        return 0.0
    st = _state(self)
    st['t'] = int(t)
    win = window_active(right, st, t)
    r = 0.0
    pend = st.get('pending')
    if pend is not None:
        if d_deal > 0 and (t - pend['t']) <= CONFIRM:
            r += R_PUNISH
            st['hits'] += 1
            st['bonus'] += R_PUNISH
            st['pending'] = None
        elif (t - pend['t']) > CONFIRM:
            st['whiffs'] += 1
            st['pending'] = None
    return r


def on_decision(self, mid_name, dx, classify):
    """决策点: 窗口内选攻击宏 → 登记 pending(每窗一次; 防连点刷)."""
    if not REW_ATK:
        return 0.0
    st = _state(self)
    if not st.get('in_window'):
        return 0.0
    if not attack_macro(mid_name, classify):
        return 0.0
    if float(dx) > DX_MAX:
        return 0.0
    if st.get('pending') is not None:
        return 0.0
    st['attempts'] += 1
    st['pending'] = {'t': st['t'], 'dx': float(dx)}
    return 0.0


def bias_now(updates, st=None):
    """R-e 当前 bias(线性衰减: updates 或墙上小时)。st=self._atk 状态或 None。"""
    if not REW_ATK or BIAS <= 0:
        return 0.0
    st = st if st is not None else {}
    if BIAS_HOURS > 0:
        el = (time.time() - st.get('t0', time.time())) / 3600.0
        return BIAS * max(0.0, 1.0 - el / BIAS_HOURS)
    u0 = st.get('u0')
    if u0 is None:
        return BIAS
    el = max(0, int(updates) - int(u0))
    return BIAS * max(0.0, 1.0 - el / float(max(1, BIAS_DECAY)))


def bias_for(self, updates, mask, n_macros, classify, names):
    """窗口内对攻击类宏(未被掩码)加 bias; 返回数组(无窗口/关闭=None)。"""
    st = getattr(self, '_atk', None)
    b = bias_now(updates, st)
    if b <= 0 or st is None or not st.get('in_window'):
        return None
    arr = None
    for i in range(n_macros):
        if mask is not None and not mask[i]:
            continue
        if attack_macro(names[i], classify):
            if arr is None:
                arr = [0.0] * n_macros
            arr[i] = b
    return arr


def whiff_mult(dx, in_window, cls, is_bullet=None):
    """R-d: 窗口内 ×1.0(不加重); 非窗口近距 ×1.2; 远距射击 ×0.5; 远距近战 ×1.2。"""
    if not REW_ATK:
        return 1.0
    dx = abs(float(dx if dx is not None else 0.0))
    if in_window:
        return 1.0
    if dx < 250.0:
        return WHIFF_NEAR
    if dx >= 400.0:
        if is_bullet is None:
            is_bullet = (cls == 'BULLET')
        if is_bullet:
            return WHIFF_FAR
        return WHIFF_MELEE_FAR
    return 1.0


def startup_line():
    return ('[rew_atk] %s punish=%.2f window=%d confirm=%d dx_max=%.0f '
            'bias=%.2f decay=%d bias_hours=%.0f whiff_near=%.2f far=%.2f '
            'melee_far=%.2f' % (
                'ON' if REW_ATK else 'OFF', R_PUNISH, WINDOW, CONFIRM, DX_MAX,
                BIAS, BIAS_DECAY, BIAS_HOURS, WHIFF_NEAR, WHIFF_FAR,
                WHIFF_MELEE_FAR))
