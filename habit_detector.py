# -*- coding: utf-8 -*-
"""R61r(E5): 坏习惯检测与惩罚演示 — 教学层"针对性教学"能力.

设计(可行性报告§3"教学性"):
  检测学员的重复性坏习惯 → 展示AI如何惩罚该习惯 → 学员理解并改正.

  与一般教学("标准应对是X")不同: 坏习惯教学是**针对性**的 —
  "你总是起身蹲防, AI用中段择惩罚你" 是个人化反馈.

坏习惯定义(攻略常见+可从动作序列检测):
  1. 起身总是蹲防 → 中段择/空择惩罚
  2. 被压总是后跳 → 前冲追击/空择惩罚
  3. 远距总是立防 → 弹幕牵制/前冲压制惩罚
  4. 空中总是受身 → 受身读取/空择惩罚
  5. 灵力空仍出招 → 空挥惩罚/投技惩罚
"""
from __future__ import annotations

import numpy as np


# ---- 坏习惯定义(条件→检测阈值→惩罚方案→讲解文本) ----
HABITS = {
    'wakeup_crouch_guard': {
        'label': '起身总是蹲防',
        'desc': '每次被击倒起身后都蹲防 — 对手用中段/空择轻松破',
        'detect': lambda seq: _detect_wakeup_guard(seq, 'crouch'),
        'threshold': 0.7,   # 70%以上起身蹲防=习惯
        'punishment': '择·中段(前冲→6A overhead)或压起身·空(j2A打逆)',
        'counter_play': '起身混合选择: 跳/防/反/穿 — 不要固定蹲防',
        'severity': '高',   # 高=严重劣势, 中=损失机会, 低=小失误
    },
    'wakeup_stand_guard': {
        'label': '起身总是立防',
        'desc': '起身后总站着防 — 对手用下段攻击破',
        'detect': lambda seq: _detect_wakeup_guard(seq, 'stand'),
        'threshold': 0.7,
        'punishment': '择·下段(前冲→2A low)或压起身·延迟(2A二择)',
        'counter_play': '蹲防挡下段, 或直接跳/反 — 混合起身选项',
        'severity': '高',
    },
    'pressure_backjump': {
        'label': '被压总是后跳',
        'desc': '被压制时总往后跳 — 对手前冲追击或空择',
        'detect': lambda seq: _detect_pressure_response(seq, 'backjump'),
        'threshold': 0.6,
        'punishment': '前冲→空择(j2A追击) 或 DA(冲刺攻击)',
        'counter_play': '结界(DD)逃压比后跳安全 — 后跳有落地硬直',
        'severity': '中',
    },
    'far_stand_guard': {
        'label': '远距总是立防',
        'desc': '远距离站着不动防 — 浪费空间, 对手自由接近',
        'detect': lambda seq: _detect_far_passive(seq),
        'threshold': 0.5,
        'punishment': '弹幕牵制(5B/5C)或前冲压制(DA)',
        'counter_play': '远距应主动: 弹幕牵制/前冲接近/高跳 — 不要站桩',
        'severity': '低',
    },
    'empty_spirit_attack': {
        'label': '灵力空仍出招',
        'desc': '灵力不足仍按攻击 — 攻击被吞(空挥), 白送硬直',
        'detect': lambda seq: _detect_empty_spirit(seq),
        'threshold': 0.3,
        'punishment': '对手直接投技(A+D)或前冲攻击 — 空挥硬直是破绽',
        'counter_play': '灵力<100时选移动/防御/结界 — 攻击键会被吞',
        'severity': '高',
    },
}


def _wakeup_samples(seq, win=10):
    """起身观察窗采样(从零#2 P1-F修复).
    原版只录起身转帧的act<50 — 防御硬直态(150-166)永不入样本,
    "起身蹲防/立防"两检测器实际只能测"起身蹲着待机"。
    修: 起身后win帧内取最强意图 — 防御态优先(150-166), 否则首个
    非待机行为。seq元素: (帧, 自身action, ...)。"""
    downs = {88, 89, 97, 98, 100, 143, 145}
    windows = []
    win_buf = None
    prev_down = False
    for row in seq:
        act = row[1]
        is_down = act in downs
        if prev_down and not is_down:
            win_buf = [act]        # 起身帧起开窗
        elif win_buf is not None:
            win_buf.append(act)
            if len(win_buf) >= win:
                windows.append(win_buf)
                win_buf = None
        prev_down = is_down
    if win_buf is not None:
        windows.append(win_buf)
    out = []
    for wb in windows:
        guard_a = next((a for a in wb if 150 <= a <= 166), None)
        if guard_a is not None:
            out.append(guard_a)
        else:
            first_a = next((a for a in wb if a > 0), 0)
            out.append(first_a)
    return out


def _detect_wakeup_guard(seq, guard_type):
    """起身行为检测(分类见HABITS). seq = [(帧, 自身action, ...), ...]"""
    wakeups = _wakeup_samples(seq)
    if not wakeups:
        return 0.0
    if guard_type == 'crouch':
        # 蹲防系: 154-157(正防下段)/163-166(错防下段)/蹲姿(1-3)
        crouch = sum(1 for a in wakeups
                     if 154 <= a <= 157 or 163 <= a <= 166 or 1 <= a <= 3)
    else:
        # 立防系: 150-153/159-162/站立(0)
        crouch = sum(1 for a in wakeups
                     if 150 <= a <= 153 or 159 <= a <= 162 or a == 0)
    return crouch / len(wakeups)


def _detect_pressure_response(seq, resp_type, hot=12):
    """被压行为检测(从零#2 P1-F修复).
    原版opp_attacking初始化False后从未置真 — 恒返回0.0(死检测器)。
    修: seq元素含对手action(第4位, 3元组向后兼容=无对手数据时退化为
    不检测), 对手攻击(300-598)后hot帧为受压窗, 窗内自身非攻击动作
    =受压应对。"""
    responses = []
    opp_hot = 0
    for row in seq:
        act = row[1]
        opp_a = row[3] if len(row) > 3 else 0
        if 300 <= opp_a <= 598:
            opp_hot = hot
        if opp_hot > 0 and act > 3 and not (300 <= act <= 598):
            responses.append(act)
        opp_hot = max(0, opp_hot - 1)
    if not responses:
        return 0.0
    if resp_type == 'backjump':
        bj = sum(1 for a in responses if a == 8)   # 后跳
        return bj / len(responses)
    return 0.0


def _detect_far_passive(seq):
    """远距被动检测."""
    passive = 0
    total = 0
    for f, act, spirit in seq:
        # 简化: 立防+待机 = 被动
        if act == 0 or 150 <= act <= 153:
            passive += 1
        total += 1
    return passive / max(total, 1)


def _detect_empty_spirit(seq):
    """空灵力出招检测."""
    attacks = 0
    empty_attacks = 0
    for f, act, spirit in seq:
        if 300 <= act <= 598:   # 攻击动作
            attacks += 1
            if spirit < 100:
                empty_attacks += 1
    return empty_attacks / max(attacks, 1)


def detect_habits(action_seq, top=3):
    """从动作序列检测坏习惯.

    action_seq: [(帧, 自身action, 灵力[, 对手action]), ...]
    (从零#2 P1-F: 第4位对手action供被压检测 — 3元组向后兼容,
    此时pressure_backjump退化为0)
    返回: [(习惯key, 习惯dict, 检测率), ...] 按严重度排序
    """
    results = []
    for key, habit in HABITS.items():
        rate = habit['detect'](action_seq)
        if rate >= habit['threshold']:
            results.append((key, habit, rate))
    sev_order = {'高': 0, '中': 1, '低': 2}
    results.sort(key=lambda x: (sev_order.get(x[1]['severity'], 3),
                                -x[2]))
    return results[:top]


def habit_report(habits, char='reimu'):
    """生成坏习惯教学报告."""
    if not habits:
        return '未检测到明显坏习惯 — 继续保持!'
    parts = ['=== 坏习惯检测报告 ===']
    for key, h, rate in habits:
        parts.append('')
        parts.append('【%s】%s (检测率%.0f%%, 严重度%s)'
                     % (h['label'], h['desc'], rate * 100,
                        h['severity']))
        parts.append('  AI惩罚方式: %s' % h['punishment'])
        parts.append('  改正建议: %s' % h['counter_play'])
    parts.append('')
    parts.append('提示: 使用 branch_demo.py 可演示各习惯的惩罚后果')
    return '\n'.join(parts)


def punishment_macros(char_lib, habit_key):
    """返回惩罚该坏习惯的宏名列表(供branch_demo演示)."""
    punish_map = {
        'wakeup_crouch_guard': ['择·中段', '压起身·空'],
        'wakeup_stand_guard': ['择·下段', '压起身·延迟'],
        'pressure_backjump': ['前冲', 'DA', '压起身·空'],
        'far_stand_guard': ['5B', '5C', 'DA', '前冲'],
        'empty_spirit_attack': ['投技', '择·投', '前冲'],
    }
    names = punish_map.get(habit_key, [])
    # 过滤: 只返回该角色库中存在的宏
    return [n for n in names if n in char_lib.get('names', set())]
