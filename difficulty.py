# -*- coding: utf-8 -*-
"""R61q(E3): 校准难度对局 — 同一模型的多档位玩法.

设计(可行性报告§3):
  用限制性手法让同一模型在不同难度档位对弈:
  - 温度限制: 高温=更随机=更弱, 低温=更集中=更强
  - 牌组限制: 纯系统卡=无SC终结, 混合=有资源管理
  - 宏掩码限制: 禁SC/技能=只靠体术, 全开=完整战术

  三档×三维度 = 灵活的难度阶梯(教学用Easy, 检验用Hard, 竞技Full).

用法:
  from difficulty import DifficultyController, DIFFICULTY_PRESETS
  ctrl = DifficultyController('normal')
  mask = ctrl.apply_mask(base_mask, char_lib)
  temp = ctrl.temperature(model_temp)
  deck = ctrl.sample_deck(char_id, rng)
"""
from __future__ import annotations

import numpy as np


# ---- 难度预设(三维限制: 温度/牌组/宏掩码) ----
DIFFICULTY_PRESETS = {
    'easy': {
        'label': '简单',
        'desc': '高随机+纯系统卡+禁SC/技能 — 入门体验',
        'temp_boost': 2.5,      # 温度加成(模型温度+此值)
        'deck_mode': 'system',   # 纯系统卡(无SC)
        'ban_sc': True,          # 禁符卡宏
        'ban_skill': True,       # 禁指令必杀
        'ban_combo': False,      # 允许基础连段
    },
    'normal': {
        'label': '普通',
        'desc': '中随机+混合卡组+禁SC — 有压迫但可反',
        'temp_boost': 1.2,
        'deck_mode': 'mixed',    # 混合(有技能卡无SC)
        'ban_sc': True,
        'ban_skill': False,
        'ban_combo': False,
    },
    'hard': {
        'label': '困难',
        'desc': '低随机+完整卡组+全宏 — 认真对弈',
        'temp_boost': 0.0,       # 模型原始温度
        'deck_mode': 'full',     # 完整采样(含SC)
        'ban_sc': False,
        'ban_skill': False,
        'ban_combo': False,
    },
    'full': {
        'label': '全力',
        'desc': '最优温度+完整卡组+全宏 — 竞技水平',
        'temp_boost': -0.3,      # 略低于模型温度(更集中)
        'deck_mode': 'full',
        'ban_sc': False,
        'ban_skill': False,
        'ban_combo': False,
    },
}


class DifficultyController:
    """难度控制器 — 对SideDriver/训练器施加限制性手法."""

    def __init__(self, level: str = 'normal'):
        if level not in DIFFICULTY_PRESETS:
            raise ValueError('未知难度: %s (可用: %s)'
                             % (level, list(DIFFICULTY_PRESETS)))
        self.level = level
        self.preset = DIFFICULTY_PRESETS[level]

    @property
    def label(self) -> str:
        return self.preset['label']

    @property
    def desc(self) -> str:
        return self.preset['desc']

    def temperature(self, model_temp: float) -> float:
        """调整采样温度(高温=随机/弱, 低温=集中/强)."""
        t = model_temp + self.preset['temp_boost']
        return max(0.3, min(4.0, t))

    def apply_mask(self, base_mask, char_lib) -> np.ndarray:
        """在基础掩码上叠加难度限制(禁SC/技能等).
        从零#2(产品面P2): ban_sc原只按lib['sc']名集禁SC宏 — 脚本含
        sc:步的TM连段漏禁; easy/normal牌组无SC卡, 选中它=符卡状态机
        空转整局(自毁式宏而非禁用)。修: 脚本含sc:步者一并掩掉。"""
        mask = base_mask.copy()
        if self.preset['ban_sc']:
            _sc_names = set(char_lib.get('sc', set()))
            for i, (name, script) in enumerate(char_lib['macros']):
                if i >= len(mask):
                    break
                if name in _sc_names:
                    mask[i] = False
                    continue
                if any(isinstance(k, str) and k.startswith('sc:')
                       for k, _f in script):
                    mask[i] = False
        if self.preset['ban_skill']:
            for name in char_lib.get('skill', set()):
                idx = char_lib['names'].index(name) \
                    if name in char_lib['names'] else -1
                if idx >= 0:
                    mask[idx] = False
        if not mask.any():
            mask = base_mask     # 全禁时回退(保底)
        return mask

    def sample_deck(self, char_engine_id: int, rng) -> list:
        """按难度采样牌组."""
        if self.preset['deck_mode'] == 'system':
            from deck_sampler import _SYSTEM_IDS
            return list(_SYSTEM_IDS[:20])
        # mixed/full → 用标准采样器
        from deck_sampler import sample_deck
        ratio = 0.5 if self.preset['deck_mode'] == 'mixed' else 0.8
        return sample_deck(char_engine_id, rng, ratio)

    def summary(self) -> str:
        p = self.preset
        return ('[%s] %s | 温度%+.1f 牌组%s SC%s技能%s'
                % (self.level, p['label'], p['temp_boost'],
                   p['deck_mode'], '禁' if p['ban_sc'] else '开',
                   '禁' if p['ban_skill'] else '开'))


def difficulty_ladder(games=3):
    """生成难度阶梯对局计划(Easy→Normal→Hard各N局)."""
    plan = []
    for level in ('easy', 'normal', 'hard'):
        ctrl = DifficultyController(level)
        plan.append({
            'level': level,
            'label': ctrl.label,
            'games': games,
            'desc': ctrl.desc,
        })
    return plan


def calibrate(matchup_history: list) -> tuple:
    """根据战绩自动推荐难度档位.

    matchup_history: [{'level': 'easy', 'win': True}, ...]
    返回: (推荐难度, 理由)
    """
    if not matchup_history:
        return 'easy', '无历史 — 从简单开始'
    recent = matchup_history[-10:]
    wr = sum(1 for m in recent if m.get('win')) / len(recent)
    cur = recent[-1].get('level', 'easy') if recent else 'easy'
    if wr >= 0.7:
        # 胜率过高 → 升难度
        order = ['easy', 'normal', 'hard', 'full']
        idx = order.index(cur) if cur in order else 0
        nxt = order[min(idx + 1, len(order) - 1)]
        return nxt, ('近%d局胜率%.0f%% ≥70%% → 升至%s'
                     % (len(recent), wr * 100, nxt))
    if wr < 0.3:
        # 胜率过低 → 降难度
        order = ['easy', 'normal', 'hard', 'full']
        idx = order.index(cur) if cur in order else 1
        prv = order[max(idx - 1, 0)]
        return prv, ('近%d局胜率%.0f%% <30%% → 降至%s'
                     % (len(recent), wr * 100, prv))
    return cur, ('近%d局胜率%.0f%% — 维持%s'
                 % (len(recent), wr * 100, cur))
