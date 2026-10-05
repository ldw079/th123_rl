# -*- coding: utf-8 -*-
"""R47卡组采样器(可行性报告天花板2): 训练局的deck从恒系统卡1-20
改为按角色合法卡池采样 — 技能卡(100+)/符卡(200+)入手激活整套
技能子系统(等级特征/SC宏门控/等级条件宏)。

来源: card_tables.py(解包CSV测量级) + mod侧isDeckValid白名单
(mod network.cpp: 每卡≤4张; 系统卡≤20; 技能卡100..112+; SC需在
角色合法表内)。

采样策略(课程化):
- 前期(前100局): 50%系统卡 / 50%混合(技能+SC入池)
- 后期: 20%系统卡 / 80%混合 — 给SC宏+技能升级足够的触发密度
"""
from __future__ import annotations

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card_tables import CHAR_CARD_TABLES, SYSTEM_CARDS  # noqa: E402

# 系统卡合法id集合(mod: card<=20)
_SYSTEM_IDS = sorted(cid for cid, _n, _c in SYSTEM_CARDS)

# 每角色合法SC(200+)id — card_tables只含角色专属
_CHAR_SC_IDS = {}
_CHAR_SKILL_IDS = {}
for _cid, _cards in CHAR_CARD_TABLES.items():
    _CHAR_SC_IDS[_cid] = sorted(int(i) for i, _n, _c in _cards
                                if int(i) >= 200)
    _CHAR_SKILL_IDS[_cid] = sorted(int(i) for i, _n, _c in _cards
                                   if 100 <= int(i) < 200)

# mod侧技能上限: 112+帕秋莉3=115, 我们表内数据即白名单子集


def sample_deck(char_engine_id: int, rng: random.Random,
                mixed_ratio: float = 0.5) -> list:
    """采样一份20张卡组。

    mixed_ratio: 混合卡组概率(系统卡vs角色卡池).
    角色卡池: 技能卡池(每角色12张)+SC池(每角色8-15张)随机填充,
    技能:SC约3:1(升级路线比终结大招更需要密度).
    """
    if rng.random() > mixed_ratio:
        return list(_SYSTEM_IDS[:20])   # 纯系统卡(保证基础技能全解锁)

    skills = _CHAR_SKILL_IDS.get(char_engine_id, [])
    scs = _CHAR_SC_IDS.get(char_engine_id, [])
    if not skills and not scs:
        return list(_SYSTEM_IDS[:20])

    deck = []
    # 技能卡: 从12张池中抽4-6张各×3-4(升级路线密度)
    n_skill_types = rng.randint(4, min(6, len(skills)))
    for sid in rng.sample(skills, n_skill_types):
        deck.extend([sid] * rng.randint(3, 4))
    # SC: 从池中抽2-4张各×1-2 (R51修复: 上界用len(scs)而非len(skills))
    if scs:
        n_sc_types = rng.randint(2, min(4, len(scs)))
        for sid in rng.sample(scs, n_sc_types):
            deck.extend([sid] * rng.randint(1, 2))
    # 填充系统卡到20
    while len(deck) < 20:
        deck.append(rng.choice(_SYSTEM_IDS))
    return deck[:20]


def curriculum_ratio(episode: int) -> float:
    """课程化混合比例: 前期50%混合→后期80%混合"""
    if episode < 100:
        return 0.5
    return min(0.8, 0.5 + (episode - 100) * 0.001)
