# -*- coding: utf-8 -*-
"""R49: 帧级事件检测与反应规则库(技法覆盖分析L3时序墙的破壁)。

设计(基于攻略167项技法的帧窗数据):
- 事件驱动: 在宏执行中逐帧检测关键事件(打防/对手起手/起身/DD窗),
  触发时**清队+帧级反应** — 与R34防御中断同构但事件面更广
- 反应规则库: 攻略已给出全部帧窗值(DD 15F/小跳 6F/插动 6-13F),
  硬编码为"事件→延迟N帧→出Y"规则 — RL学"何时不反应",规则管执行

事件类型(优先级从高到低):
  GUARDSTUN_ENTER  被防(防御硬直开始) — DD/灵反/灵击/插动的窗口
  OPP_STARTUP      对手攻击启动帧(300-598且非自身已防) — 插动/凹/防御
  WAKEUP_WINDOW    自身起身(倒地→起身过渡) — 起身技/防御/穿人选择
  AIRTECH_WINDOW   自身受身窗口(untech倒计时到0) — 受身方向选择
  NEAR_MISS        对手在攻击范围边缘且自身可移动 — 打逆/表里择

每个事件有:
  - 帧窗(多少帧内必须反应, 超时=放弃)
  - 反应宏候选表(按情境条件过滤)
  - 优先级(高优先级事件覆盖低优先级)
"""
from __future__ import annotations

import numpy as np

from feat_builder import eff_untech  # BH-4.2: untech动作门(bug档)

# ---- 事件定义 ----
E_NONE = 0
E_GUARDSTUN = 1     # 被防开始
E_GUARDSTUN_END = 2 # 防御硬直结束(可以行动)
E_OPP_STARTUP = 3   # 对手攻击启动(300-598)
E_WAKEUP = 4        # 自身起身
E_AIRTECH = 5       # 自身受身窗口
E_NEAR_MISS = 6     # 对手攻击末端(可插动)
E_OPP_GUARD = 7     # 对手进入防御态(我方压制中 — 换磨灵/换择/撤)
E_COMBO_DROP = 8    # 连段中断(对手untech恢复而我未在攻击 — 收招/防/重入)
E_OPP_JUMP = 9      # 对手起跳(JZ-3.3: 确认起跳→对空反应窗)

# R52: 事件名映射(train_tm的[帧级事件]日志用)
EV_NAMES = {
    E_NONE: 'E_NONE',
    E_GUARDSTUN: 'E_GUARDSTUN',
    E_GUARDSTUN_END: 'E_GUARDSTUN_END',
    E_OPP_STARTUP: 'E_OPP_STARTUP',
    E_WAKEUP: 'E_WAKEUP',
    E_AIRTECH: 'E_AIRTECH',
    E_NEAR_MISS: 'E_NEAR_MISS',
    E_OPP_GUARD: 'E_OPP_GUARD',
    E_COMBO_DROP: 'E_COMBO_DROP',
    E_OPP_JUMP: 'E_OPP_JUMP',
}

# R61d(A3裁决): 防御硬直族 = 150-166 除158 — 150-157正确防御硬直
# (SokuLib: RIGHTBLOCK_*_BLOCKSTUN; hitlab实测151于正防接触) +
# 159-166错误防御硬直。158=空防状态/167=无枚举, 均不入边沿。
# JZ-3.1(2026-10-14): 正防/错防拆分 — 攻略(attack_level_stun.json
# guard_actions): 错防中DD/铜钱/灵反(防御反击)全部封锁, 仅可切换
# 防御段位; 错防硬直也更长(11/19/27/31F vs 9/15/21/27F)。
_GUARD_STUN_IDS = frozenset(range(150, 167)) - {158}
_CORRECT_GUARD_IDS = frozenset(range(150, 158))    # 正防硬直
_WRONG_GUARD_IDS = frozenset(range(159, 167))      # 错防硬直
# JZ-3.1: 错防中封锁的escape反应(默认掩蔽, 策略在事件窗外仍自由 —
# "默认掩蔽+策略可学习解除"而非硬规则)。
# 掩蔽集=攻略明文(fangyu.txt:453"错防的话DD和灵反和铜钱都不能使用"):
# DD(结界2/4)/铜钱/灵反(=身代わり人形, 28F反击, JZ-4入卡后加名)。
# **灵击札不在封锁列**(灵击12F低档反击保持可用 — fangyu.txt:460反击表
# 三卡并列而错防禁令只点灵反/铜钱/DD; 2026-10-14卡研究修正, 原版误列)
_WRONG_GUARD_BANNED = frozenset({
    '结界2', '结界4',            # DD回避结界(2DD/4DD)
    '卡·铜钱',                    # 宵越しの銭(sc:12, JZ-4入卡)
    '卡·人偶',                    # 身代わり人形=灵反(sc:4, JZ-4入卡)
})
# R61d: 真倒地集(起身事件只认这些 → 可行动的转出)
_TRUE_DOWN_ACTS = frozenset({88, 89, 97, 98, 100, 143, 145})

# 攻略帧窗(测量级, 来源: 钢琴男攻略四部)
FRAME_WINDOWS = {
    E_GUARDSTUN: 15,     # DD回避结界输入窗15F
    E_GUARDSTUN_END: 8,  # 防后有利/不利判定窗
    E_OPP_STARTUP: 12,   # 插动反应窗(最快6F+缓冲)
    E_WAKEUP: 20,        # 起身无敌+选择窗
    E_AIRTECH: 15,       # 受身15F完全无敌
    E_NEAR_MISS: 10,     # 攻击末端插动窗
    E_OPP_GUARD: 8,      # 换择窗口(方案线B-1: 对手防御确立→磨灵/择/撤)
    E_COMBO_DROP: 6,     # 收招窗口(方案线B-2: 连段确认失败→攻防转换)
    # JZ-3.3: 大跳上升段被COUNTER窗21F(jump_recovery_windows.json
    # super_jump.counter_window) — "确认对手起跳→升JA/对空"是全游戏
    # 最确定的帧数收益之一(立回压制攻略); 小跳窗更短, 事件窗取
    # 最长可反应窗, 迟反应落空由执行器自然止损
    E_OPP_JUMP: 21,
}

# 反应宏候选表: 事件→[(宏名模式, 条件, 优先级)]
# 宏名用前缀匹配(兼容三角色库的命名差异)
REACTION_TABLE = {
    E_GUARDSTUN: [
        ('结界2', 'down_guard', 0.7),      # 2DD逃压(降权: R50体检A2被动性)
        ('结界4', 'back_guard', 0.6),       # 4DD后撤
        ('立防',  'always', 0.4),           # 继续防(降权: 原默认反应加剧被动)
        ('蹲防',  'opp_low', 0.4),          # 对手下段习惯
        ('后跳',  'always', 0.5),           # 后跳脱离(升权: 主动逃压)
        ('623B',  'reversal_ok', 0.5),      # 凹升龙(升权: 主动反制)
        # 线B-3审查补(2026-10-14): 灵击札=无敌防反脱连段, 打防本职选项
        ('卡·灵击札', 'always', 0.6),       # 无敌防反(SC门控管可用性)
    ],
    E_GUARDSTUN_END: [
        ('5A',   'advantage', 0.8),         # 有利帧抢攻
        ('2A',   'advantage', 0.7),         # 下段抢
        ('前冲', 'advantage', 0.6),         # 前冲压制
        ('后退', 'disadvantage', 0.5),      # 不利撤退(降权)
        ('立防', 'disadvantage', 0.5),      # 不利继续防(降权)
    ],
    E_OPP_STARTUP: [
        ('立防',  'always', 0.5),           # 最安全反应(降权: 原最高→被动)
        ('蹲防',  'opp_low_hab', 0.5),      # 对手下段习惯
        ('623B',  'reversal_ok', 0.6),      # 凹升龙(升权: 主动反制)
        ('623C',  'reversal_ok', 0.6),      # 凹升龙C
        ('2A',    'close_range', 0.7),      # 近距插动(升权: 主动abare)
        ('DA',    'mid_range', 0.5),        # 中距冲刺插
        # 线B-3审查补(2026-10-14): 远程起手缺擦弹回避
        ('高跳',  'far_range', 0.4),        # 高跳GRAZE穿弹(远程起手回避)
    ],
    E_WAKEUP: [
        ('起身穿', 'always', 0.7),           # 移动起身穿人
        ('立防',   'opp_pressure', 0.4),     # 对手压起身→防(降权)
        ('623B',   'reversal_ok', 0.6),      # 起身凹
        ('后跳',   'always', 0.4),           # 后跳逃离(降权)
        ('受身',   'always', 0.4),           # 受身(倒地追打用)
    ],
    E_AIRTECH: [
        ('受身',  'always', 0.6),            # 受身(方向由mirror处理)
        ('jA',    'always', 0.6),            # 空中反击
        ('jB',    'always', 0.5),            # 空中弹幕
        # 线B-3审查补(2026-10-14): 受身后被追打缺防御选项
        ('空防',  'always', 0.5),            # 空中防御(对空追打)
    ],
    E_NEAR_MISS: [
        ('5A',   'close_range', 0.7),        # 近距插动
        ('2A',   'close_range', 0.6),        # 下段插
        ('前冲', 'mid_range', 0.5),          # 中距前冲
        ('5B',   'far_range', 0.4),          # 远距弹幕
    ],
    # 线B-1(2026-10-14): 对手进入防御态 → 我方压制应变
    # (此前此信息只在cconfirm门内间接感知; 事件级触发让策略更早介入)
    E_OPP_GUARD: [
        ('5B',   'always', 0.6),            # 弹幕磨灵(主力应防)
        ('2B',   'always', 0.6),            # 下段弹幕磨灵
        ('5C',   'far_range', 0.5),         # 远距重弹幕
        ('6A',   'close_range', 0.6),       # 近距换择(中段)
        ('3A',   'close_range', 0.5),       # 下段换择
        ('后退', 'always', 0.4),            # 撤退重整(降权: 防被动)
        ('结界4', 'back_guard', 0.4),       # 后撤结界
    ],
    # 线B-2(2026-10-14): 连段确认失败(对手恢复而我未在攻) → 收招/防/重入
    E_COMBO_DROP: [
        ('后退', 'always', 0.5),            # 收招撤退
        ('立防', 'always', 0.5),            # 防对手反打
        ('前冲', 'always', 0.5),            # 压制重入
        ('5B',   'far_range', 0.5),         # 远距弹幕盖
    ],
    # JZ-3.3(2026-10-14): 对手起跳 → 对空反应(确认起跳窗=确定帧数收益)
    # 注意: 不用623B — 萃香623B=萃鬼投技(地面投, 非对空), 反应表按
    # 宏名跨库解析会张冠李戴; 对空由3A/6A承担
    E_OPP_JUMP: [
        ('3A',   'close_range', 0.65),      # 对空主力(reimu库无→自动跳过)
        ('6A',   'close_range', 0.5),       # 通用对空
        ('高跳', 'mid_range', 0.45),        # 跳起对空(air-to-air)
        ('5B',   'far_range', 0.45),        # 对空弹幕
        ('前冲', 'always', 0.4),            # 横穿落点
        ('空防', 'always', 0.35),           # 保守对跳入
    ],
}


class FrameEventDetector:
    """逐帧事件检测器 — 在_run_episode的帧循环中调用。"""

    def __init__(self):
        self.last_action = 0
        self.last_opp_action = 0
        self.last_untech = 0
        self.last_opp_untech = 0
        self.guardstun_frames = 0
        self.opp_startup_seen = False
        self.event_cooldown = {}   # 事件→剩余冷却帧(防重复触发)
        # JZ-3.1: 正防/错防标记(最近一次GUARDSTUN/OPP_GUARD的类别)
        self.last_guard_kind = None        # 'correct'|'wrong'|None
        self.last_opp_guard_kind = None    # 对手侧镜像
        self.guard_kind_counts = {'correct': 0, 'wrong': 0}
        # JZ-3.3: 对手离地边沿基线
        self.last_opp_air = False

    def detect(self, left: dict, right: dict, frozen: bool) -> tuple:
        """检测当前帧的帧级事件。

        left/right: 105B包解析的玩家状态dict
        frozen: 当前是否在hitstop(冻结时不触发事件)
        返回: (事件类型, 事件帧窗) 或 (E_NONE, 0)
        """
        if frozen:
            # 冻结时更新基线但不触发
            self.last_action = left.get('action', 0)
            self.last_opp_action = right.get('action', 0)
            self.last_opp_air = bool(right.get('airBorne', False))
            self._tick_cooldown()
            return E_NONE, 0

        my_a = left.get('action', 0)
        opp_a = right.get('action', 0)
        # BH-4.2: 过动作门(残留untech会伪造AIRTECH/COMBO_DROP边沿)
        untech = eff_untech(left)

        # 冷却
        self._tick_cooldown()

        # --- 事件1: 打防开始(防御硬直态) ---
        # R61d(A3裁决, 2026-10-05 hitlab+SokuLib枚举): 150-157=正确防御硬直
        # (枚举RIGHTBLOCK_*_BLOCKSTUN; hitlab实测正防接触出151, 纯持防恒为
        # 5/8走位无150族 → R21"150-153=持防姿态"读法错, 姿态不占action ID)。
        # R51改159-167只留错防族=正确防御(大多数)不可见(从零审计F-13)。
        # 158=空防状态(非硬直边沿)不入enter沿; 167=SokuLib无此ID不入。
        if (my_a in _GUARD_STUN_IDS
                and self.last_action not in _GUARD_STUN_IDS):
            if self._can_fire(E_GUARDSTUN):
                self._fire(E_GUARDSTUN)
                # JZ-3.1: 携带正/错标记(150-157正防/159-166错防)
                self.last_guard_kind = ('wrong' if my_a in _WRONG_GUARD_IDS
                                        else 'correct')
                self.guard_kind_counts[self.last_guard_kind] += 1
                self.last_action = my_a
                self.last_opp_action = opp_a
                return E_GUARDSTUN, FRAME_WINDOWS[E_GUARDSTUN]

        # --- 事件2: 防御硬直结束 ---
        if (self.last_action in _GUARD_STUN_IDS
                and my_a not in _GUARD_STUN_IDS):
            if self._can_fire(E_GUARDSTUN_END):
                self._fire(E_GUARDSTUN_END)
                self.last_action = my_a
                self.last_opp_action = opp_a
                return E_GUARDSTUN_END, FRAME_WINDOWS[E_GUARDSTUN_END]

        # --- 事件2.5(JZ-3.3): 对手起跳(离地边沿 → 对空反应窗) ---
        # my_a<50=自身可行动(受击/攻击中无力对空, 同事件4口径)
        opp_air = bool(right.get('airBorne', False))
        if opp_air and not self.last_opp_air and my_a < 50:
            if self._can_fire(E_OPP_JUMP):
                self._fire(E_OPP_JUMP)
                self.last_action = my_a
                self.last_opp_action = opp_a
                self.last_opp_air = opp_air
                return E_OPP_JUMP, FRAME_WINDOWS[E_OPP_JUMP]

        # --- 事件3: 对手攻击启动(300-598) ---
        if (300 <= opp_a <= 598
                and not (300 <= self.last_opp_action <= 598)
                and my_a < 100
                and not (150 <= my_a <= 167)):
            if self._can_fire(E_OPP_STARTUP):
                self._fire(E_OPP_STARTUP)
                self.last_action = my_a
                self.last_opp_action = opp_a
                return E_OPP_STARTUP, FRAME_WINDOWS[E_OPP_STARTUP]

        # --- 事件4: 起身窗口(从真倒地→可行动) ---
        # R61d(A3裁决): 真倒地集=88/89(空中受击砸地)+97/98(倒地弹跳/静止)
        # +100(被投)+143/145(被压溃) — SokuLib枚举语义, 全部导向倒地。
        # R51版用全受击族(50-98)把站立/蹲姿/普通空中受击的恢复也当起身
        # (hitlab H1实证: 5A命中后0→50×20帧→0=受击恢复非起身, 但旧沿
        # 在50→0瞬间误触WAKEUP劫持行为 — 从零审计F-12)。
        _DOWN_ACTS = _TRUE_DOWN_ACTS
        if my_a < 50 and self.last_action in _DOWN_ACTS:
            if self._can_fire(E_WAKEUP):
                self._fire(E_WAKEUP)
                self.last_action = my_a
                self.last_opp_action = opp_a
                return E_WAKEUP, FRAME_WINDOWS[E_WAKEUP]

        # --- 事件5: 受身窗口(untech从>0到0) ---
        if untech == 0 and self.last_untech > 0:
            # 且自身在空中
            if left.get('airBorne', False):
                if self._can_fire(E_AIRTECH):
                    self._fire(E_AIRTECH)
                    self.last_action = my_a
                    self.last_opp_action = opp_a
                    self.last_untech = untech
                    return E_AIRTECH, FRAME_WINDOWS[E_AIRTECH]

        # --- 事件6: 对手攻击末端(可能可插动) ---
        # 简化: 对手从攻击态→非攻击态, 且近距
        dx = abs(right.get('position.x', 0) - left.get('position.x', 0))
        if (not (300 <= opp_a <= 598)
                and (300 <= self.last_opp_action <= 598)
                and dx < 250):
            if self._can_fire(E_NEAR_MISS):
                self._fire(E_NEAR_MISS)
                self.last_action = my_a
                self.last_opp_action = opp_a
                return E_NEAR_MISS, FRAME_WINDOWS[E_NEAR_MISS]

        # --- 事件7(线B-1): 对手进入防御态(我方压制应变) ---
        # 沿: opp_a进入GUARD_STUN族且last不在(与事件1镜像, 视角反转)
        # BH-4.2: 过动作门(自由飞翔的残留untech不构成COMBO_DROP沿)
        opp_untech = eff_untech(right)
        if (opp_a in _GUARD_STUN_IDS
                and self.last_opp_action not in _GUARD_STUN_IDS):
            if self._can_fire(E_OPP_GUARD):
                self._fire(E_OPP_GUARD)
                # JZ-3.1: 对手正/错防标记(错防=对手不能DD/铜钱/灵反,
                # 且硬直更长 → 压制继续/换择的直读信号)
                self.last_opp_guard_kind = ('wrong' if opp_a in _WRONG_GUARD_IDS
                                            else 'correct')
                self.last_action = my_a
                self.last_opp_action = opp_a
                self.last_opp_untech = opp_untech
                return E_OPP_GUARD, FRAME_WINDOWS[E_OPP_GUARD]

        # --- 事件8(线B-2): 连段中断(对手untech恢复而我未在攻击) ---
        # 沿: opp_untech从>0到0 且 my_a<100(非攻击中=确认失败)
        if (opp_untech == 0 and self.last_opp_untech > 0
                and my_a < 100):
            if self._can_fire(E_COMBO_DROP):
                self._fire(E_COMBO_DROP)
                self.last_action = my_a
                self.last_opp_action = opp_a
                self.last_opp_untech = opp_untech
                return E_COMBO_DROP, FRAME_WINDOWS[E_COMBO_DROP]

        # 更新基线
        self.last_action = my_a
        self.last_opp_action = opp_a
        self.last_untech = untech
        self.last_opp_untech = opp_untech
        self.last_opp_air = opp_air
        return E_NONE, 0

    def _can_fire(self, event: int) -> bool:
        return self.event_cooldown.get(event, 0) <= 0

    def _fire(self, event: int):
        # 冷却: 帧窗的2倍(防止同一事件连续触发)
        self.event_cooldown[event] = FRAME_WINDOWS.get(event, 10) * 2

    def _tick_cooldown(self):
        for k in list(self.event_cooldown):
            self.event_cooldown[k] -= 1
            if self.event_cooldown[k] <= 0:
                del self.event_cooldown[k]


class ThrowInvulnTracker:
    """JZ-3.2: 对手投技无敌窗跟踪(data/guide_tables/throw_invuln.json口径)。

    无敌来源四类(攻略表): 起身10F / 防御硬直中+后10F / 起跳1F / 受身全程。
    受身全程在线不可直读(受身动作无独立观测), 以untech>0浮空近似
    (浮空连段不可投, 保守覆盖)。frozen帧不推进不更新基线 — 与
    FrameEventDetector同拍。决策点读invuln>0时掩蔽投技宏(掩码层,
    零奖励改动, 窗外策略仍自由选投)。
    """

    WAKEUP_F = 10        # 起身后投技无敌
    GUARD_AFTER_F = 10   # 防硬直结束后投技无敌
    JUMP_F = 1           # 起跳瞬间

    def __init__(self):
        self.invuln = 0
        self._last_opp_action = 0
        self._last_opp_air = False

    def feed(self, opp: dict, frozen: bool = False):
        if frozen:
            return
        if self.invuln > 0:
            self.invuln -= 1             # 帧首老化上一窗(1F窗对读者可见)
        a = opp.get('action', 0)
        air = bool(opp.get('airBorne', False))
        # BH-4.2: 过动作门(自由空中行动的残留untech不标记投技无敌)
        untech = eff_untech(opp)
        if a in _GUARD_STUN_IDS:      # 防硬直中持续刷新, 出防后余10F
            self.invuln = max(self.invuln, self.GUARD_AFTER_F + 1)
        if self._last_opp_action in _TRUE_DOWN_ACTS and a < 50:
            self.invuln = max(self.invuln, self.WAKEUP_F)
        if air and not self._last_opp_air:
            self.invuln = max(self.invuln, self.JUMP_F)
        if untech > 0:                # 浮空受身不可期(受身全程的保守近似)
            self.invuln = max(self.invuln, 1)
        self._last_opp_action = a
        self._last_opp_air = air


def _match_macro(name_pattern, macro_names):
    """反应宏名解析(从零#2 P1-H): 精确名 > 前缀 > 子串。
    原"首个startswith命中即break"使'2A'恒命中库序在前的'2A确认'
    (时间关键的防御反应实际插入带门连段; suika只是碰巧库序在尾)。
    pick_reaction与reaction_mask共用本函数 — 两处对称。"""
    if name_pattern in macro_names:
        return macro_names.index(name_pattern)
    for i, mn in enumerate(macro_names):
        if mn.startswith(name_pattern):
            return i
    for i, mn in enumerate(macro_names):
        if name_pattern in mn:
            return i
    return -1


def pick_reaction(event: int, left: dict, right: dict,
                  macro_names: list, base_mask,
                  rng) -> int:
    """从反应表中选择一个宏。

    按事件类型→反应候选表→过滤(宏存在+掩码允许+情境条件)→
    按优先级加权随机。
    返回: 宏ID 或 -1(无可用反应)
    """
    if event not in REACTION_TABLE:
        return -1
    dx = abs(right.get('position.x', 0) - left.get('position.x', 0))
    spirit = left.get('spirit', 0)
    opp_a = right.get('action', 0)

    # 情境条件判定
    def cond_ok(cond: str) -> bool:
        if cond == 'always':
            return True
        if cond == 'down_guard':
            return True    # 结界2随时可用(2DD)
        if cond == 'back_guard':
            return True
        if cond == 'opp_low':
            return dx < 200
        if cond == 'opp_low_hab':
            return dx < 250
        if cond == 'advantage':
            return True    # 简化: 防后默认可动
        if cond == 'disadvantage':
            return True
        if cond == 'reversal_ok':
            return spirit >= 200
        if cond == 'close_range':
            return dx < 200
        if cond == 'mid_range':
            return 200 <= dx < 400
        if cond == 'far_range':
            return dx >= 400
        if cond == 'opp_pressure':
            return dx < 300
        return False

    # 过滤候选(从零#2 P1-H: 精确名优先 — 原首个前缀命中即break)
    wrong_guard = (event == E_GUARDSTUN
                   and left.get('action', 0) in _WRONG_GUARD_IDS)
    candidates = []
    for name_prefix, cond, priority in REACTION_TABLE[event]:
        if wrong_guard and name_prefix in _WRONG_GUARD_BANNED:
            continue               # JZ-3.1: 错防封锁DD/铜钱/防御反击
        i = _match_macro(name_prefix, macro_names)
        if i < 0:
            continue
        if base_mask is not None and not base_mask[i]:
            continue
        if cond_ok(cond):
            candidates.append((i, priority))

    if not candidates:
        return -1

    # 加权随机(R52: numpy Generator无.choices, 用.choice+概率)
    weights_arr = np.array([p for _, p in candidates], dtype=np.float64)
    probs = weights_arr / weights_arr.sum()
    idx = int(rng.choice(len(candidates), p=probs))
    return candidates[idx][0]


def reaction_mask(event: int, left: dict, right: dict,
                  macro_names: list, base_mask) -> np.ndarray:
    """R61l(B2): 事件→策略条件化反应掩码。

    与pick_reaction同源的候选过滤, 但返回掩码而非选择 —
    策略在下一决策点从掩码约束的选项中**自主选择**(学习化),
    替代固定权重随机(原版B2目标: "从固定权重随机→策略条件化")。

    返回: (N,)bool 掩码(True=该宏是本事件的有效反应);
    全False时返回None(无可用反应, 不触发决策点)。
    """
    if event not in REACTION_TABLE:
        return None
    dx = abs(right.get('position.x', 0) - left.get('position.x', 0))
    spirit = left.get('spirit', 0)

    def cond_ok(cond: str) -> bool:
        if cond == 'always':
            return True
        if cond == 'down_guard':
            return True
        if cond == 'back_guard':
            return True
        if cond == 'opp_low':
            return dx < 200
        if cond == 'opp_low_hab':
            return dx < 250
        if cond == 'advantage':
            return True
        if cond == 'disadvantage':
            return True
        if cond == 'reversal_ok':
            return spirit >= 200
        if cond == 'close_range':
            return dx < 200
        if cond == 'mid_range':
            return 200 <= dx < 400
        if cond == 'far_range':
            return dx >= 400
        if cond == 'opp_pressure':
            return dx < 300
        return False

    out = np.zeros(len(macro_names), dtype=bool)
    wrong_guard = (event == E_GUARDSTUN
                   and left.get('action', 0) in _WRONG_GUARD_IDS)
    for name_prefix, cond, _priority in REACTION_TABLE[event]:
        if wrong_guard and name_prefix in _WRONG_GUARD_BANNED:
            continue               # JZ-3.1: 错防封锁DD/铜钱/防御反击
        # 从零#2 P1-H: 与pick_reaction同源解析(原两处continue/break不对称)
        i = _match_macro(name_prefix, macro_names)
        if i < 0:
            continue
        if base_mask is not None and not base_mask[i]:
            continue
        if cond_ok(cond):
            out[i] = True
    return out if out.any() else None
