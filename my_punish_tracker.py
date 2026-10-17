# -*- coding: utf-8 -*-
"""S-1 MyPunishTracker(合并终版方案2026-10-14, 变招×心理博弈捕获):

"我方招式类别 × 被反制结果"的滚动EMA — 双方通用组件:
在线(train_tm帧循环, 每决策点读特征)与离线(S-5专家shard后处理)
共享同一实现, 语义一致性由同一份代码保证。

类别(优先级序): GUARD_PREP > JUMP > BULLET > SKILL > MELEE > OTHER
结果: PUNISHED(我出招→被对手命中且我未命中) / LANDED / WHIFFED /
NEUTRAL(被防无伤等 — 被防≠吃亏, 不计punish)。
输出: 每类 punish_rate ∈ [0,1], EMA半衰~30s(62fps×30≈1860帧)。

判据(S-1规格原文):
  我方类别C的宏在执行 && 对手命中我方(d_take>0且对手在攻击态)
  && 我方未命中(d_deal==0) → C类punish+1
"""
from __future__ import annotations

import time

# 类别归属名集(三角色命名共通; 与lib集合求交消歧)
JUMP_NAMES = {'跳跃', '后跳', '高跳', '斜上冲', '斜后跳', '空冲',
              '空冲后', '空翔前', '空翔后', '飞翔'}
GUARD_PREP_NAMES = {'立防', '蹲防', '空防', '结界2', '结界4'}

CLASSES = ('JUMP', 'MELEE', 'BULLET', 'SKILL', 'GUARD_PREP', 'OTHER')

# 结果
PUNISHED, LANDED, WHIFFED, NEUTRAL = 0, 1, 2, 3


def classify(name, lib=None):
    """宏名→类别。优先级: GUARD_PREP > JUMP > BULLET > SKILL > MELEE。

    lib: CHAR_LIBS[char](提供bullet/skill/melee集合); None时仅按名集。
    """
    if name in GUARD_PREP_NAMES:
        return 'GUARD_PREP'
    if name in JUMP_NAMES:
        return 'JUMP'
    if lib is not None:
        if name in lib.get('bullet', ()):
            return 'BULLET'
        if name in lib.get('skill', ()):
            return 'SKILL'
        if name in lib.get('melee', ()):
            return 'MELEE'
    elif name in {'5B', '2B', '6B', '5C', '6C', 'jB', '236B', '236C'}:
        return 'BULLET'
    return 'OTHER'


class MyPunishTracker:
    """单侧punish率跟踪器。

    用法(在线): 宏开始→begin(cls, name=宏名); 每帧→frame(d_take,
    opp_attacking, d_deal); 宏结束/被打断→end()(EMA更新并返回结果)。
    用法(离线重放): 同上按shard帧序列驱动, 结果累入EMA。
    EMA: 每完成一个该类宏, rate += α·(is_punished − rate)。

    CE-1(2026-10-15): 双层结构 — 类别层(原有, 特征[330..333]/[339])
    + 宏层(per-macro EMA, 半衰~3min跨多局)。API向后兼容:
    begin(cls) 不传name时行为与原版完全一致。

    LE-3(2026-10-17, 后BH段): 即时反馈加速 — 明确被反制(PUNISHED)时
    α临时放大(事件驱动大步更新), 正常结果维持慢EMA。单实现在此,
    在线/离线同代码路径(方案v2硬约束)。加速因子=PUNISHED_SPEEDUP.
    """

    # LE-3: PUNISHED结果的α放大因子(事件驱动大步; 正常结果不变)
    PUNISHED_SPEEDUP = 3.0

    def __init__(self, alpha=0.3, macro_alpha=0.1):
        # α=0.3: ~3次同类结果内显著移动(合成验收"连跳被对空→>0.6"),
        # 同时单次 Lucky/Unlucky 不至于满格
        self.alpha = alpha
        # CE-1: 宏层EMA更慢(样本稀疏, ~10次才显著移动) + 跨局累积
        self.macro_alpha = macro_alpha
        self.rate = {c: 0.0 for c in CLASSES}
        self.n_done = {c: 0 for c in CLASSES}
        # CE-1 宏层: 宏名→(rate, n_done)
        self.macro_rate = {}
        self.macro_n = {}
        self._cur = None       # 当前宏类别
        self._cur_name = None  # CE-1: 当前宏名(None=类别-only模式)
        self._hit_taken = False
        self._hit_dealt = False
        self._contact = False  # 有任何接触(命中/被命中/被防)

    # ---- 宏生命周期 ----
    def begin(self, cls, name=None):
        """CE-1: name=宏名(可选); 不传时行为与原版一致。"""
        if self._cur is not None:
            self.end()
        self._cur = cls
        self._cur_name = name
        self._hit_taken = self._hit_dealt = self._contact = False

    def frame(self, d_take, opp_attacking, d_deal, blocked=False):
        """执行中的一帧。d_take/d_deal: 本帧伤害增量; opp_attacking:
        对手action在攻击态; blocked: 我方进入防御硬直(被防证据)。"""
        if self._cur is None:
            return
        if d_take > 0 and opp_attacking:
            self._hit_taken = True
            self._contact = True
        if d_deal > 0:
            self._hit_dealt = True
            self._contact = True
        if blocked:
            self._contact = True

    def end(self):
        """宏结束→判定结果+EMA更新。返回结果常量(无活动宏→None)。"""
        if self._cur is None:
            return None
        cls = self._cur
        name = self._cur_name
        self._cur = None
        self._cur_name = None
        if self._hit_dealt:
            outcome = LANDED
        elif self._hit_taken:
            outcome = PUNISHED       # 被命中且未命中 = 吃亏
        elif self._contact:
            outcome = NEUTRAL        # 被防无伤等
        else:
            outcome = WHIFFED
        self.n_done[cls] += 1
        is_p = 1.0 if outcome == PUNISHED else 0.0
        # LE-3: 明确被反制时α放大(事件驱动大步更新 — 惩罚→行为
        # 改变延迟缩短; 正常结果维持慢EMA防振荡)
        _alpha = self.alpha * (self.PUNISHED_SPEEDUP
                               if outcome == PUNISHED else 1.0)
        _alpha = min(_alpha, 1.0)   # α不超过1(全量更新)
        self.rate[cls] += _alpha * (is_p - self.rate[cls])
        # CE-1: 宏层EMA(慢更新+跨局累积; LE-3同加速)
        if name is not None:
            if name not in self.macro_rate:
                self.macro_rate[name] = 0.0
                self.macro_n[name] = 0
            self.macro_n[name] += 1
            _m_alpha = self.macro_alpha * (
                self.PUNISHED_SPEEDUP if outcome == PUNISHED else 1.0)
            _m_alpha = min(_m_alpha, 1.0)
            self.macro_rate[name] += _m_alpha * (
                is_p - self.macro_rate[name])
        return outcome

    # ---- 读数 ----
    def punish_rate(self, cls):
        return self.rate.get(cls, 0.0)

    def macro_punish_rate(self, name, cls=None, min_n=3):
        """CE-1: 宏级punish率(分层回退 — 样本<min_n时填类别率)。

        返回值∈[0,1]; 未见过的宏→类别率(中性起点)或0。
        """
        if name in self.macro_rate and self.macro_n[name] >= min_n:
            return self.macro_rate[name]
        # 回退: 用类别率作先验(不造没有的数据)
        if cls is not None:
            return self.rate.get(cls, 0.0)
        # 无类别也无宏数据 → 中性0
        return self.macro_rate.get(name, 0.0)

    def snapshot(self):
        return dict(self.rate)

    def macro_snapshot(self):
        """CE-1: 宏层快照(宏名→rate, 仅n≥min_n的)。"""
        return {n: r for n, r in self.macro_rate.items()
                if self.macro_n.get(n, 0) >= 3}

    def my_dominant_punished(self):
        """S-2维10辅助: 主导类(完成数最多)的punish率。"""
        if not any(self.n_done.values()):
            return 0.0
        dom = max(CLASSES, key=lambda c: self.n_done[c])
        return self.rate[dom]
