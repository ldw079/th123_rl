# -*- coding: utf-8 -*-
"""A1-1(未决问题方案§A): 被动性仪表 — "学会不输, 没学会赢"的量化.

指标(逐episode离线, 挂learner批路径 — 与series_meter同挂点理由:
episode消费即删, 批路径是唯一可持续测量点):
  1. far_bullet_share — 330px外决策中弹幕族占比(B3修正版口径:
     adx=core[4], R67c修正前B3误读core[5]=own_x把站位当距离, 首份
     基线作废);
  2. closing_rate — 相邻决策拍|dx|下降的占比(逼近倾向; 高=前压);
  3. opening_attack_rate — 开局窗口(前8个决策拍)攻击族占比.

核心列布局(vals16, 经feat_builder标定钉死, 见test_passivity_a11):
  core[4]=clip(adx/600) core[5]=own_x/620 core[7]=own_hp core[8]=opp_hp.
挂点: learner_hub批行后追加"被动曲线"行(grep口径).
"""
from __future__ import annotations

import numpy as np

ADX_COL = 4          # clip(|dx|/600, 0, 1)
FAR_PX = 330.0
ADX_SCALE = 600.0
OPENING_DECISIONS = 8   # "开局"窗口(决策拍粒度 — 帧号不入episode, 拍近似)


def episode_passivity(char, arr):
    """单episode被动指标 → (远弹份额|None, 远决策数, 逼近率, 开局攻击率)."""
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS[char]
    names = lib['names']
    n = len(arr['acts'])
    if n == 0:
        return None, 0, None, None
    n_macros = len(names)
    sides = arr['sides']
    adx = np.clip(sides[:, 2 * n_macros + ADX_COL].astype(np.float64)
                  * ADX_SCALE, 0, ADX_SCALE)
    acts = np.asarray(arr['acts'])
    far = adx >= FAR_PX
    bullet = np.array([names[a] in lib['bullet'] for a in acts], dtype=bool)
    far_share = (float(bullet[far].mean()) if far.any() else None)
    far_n = int(far.sum())
    if n >= 2:
        closing = float((np.diff(adx) < 0).mean())
    else:
        closing = None
    attack = np.array([names[a] in lib['attack'] for a in acts], dtype=bool)
    k = min(OPENING_DECISIONS, n)
    opening_atk = float(attack[:k].mean()) if k else None
    return far_share, far_n, closing, opening_atk


def passivity_line(records):
    """[(far_share|None, far_n, closing|None, opening|None)] → 汇总行."""
    fs = [r[0] for r in records if r[0] is not None and r[1] > 0]
    cl = [r[2] for r in records if r[2] is not None]
    op = [r[3] for r in records if r[3] is not None]
    far_s = ('%d%%' % round(100 * np.mean(fs)) if fs else '-')
    clo_s = ('%d%%' % round(100 * np.mean(cl)) if cl else '-')
    opn_s = ('%d%%' % round(100 * np.mean(op)) if op else '-')
    return '远弹%s(n%d) 逼近%s 开局攻%s' % (
        far_s, sum(r[1] for r in records), clo_s, opn_s)
