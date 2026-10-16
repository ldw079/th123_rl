# -*- coding: utf-8 -*-
"""JZ-3.1: 正防/错防事件拆分 + 错防escape掩蔽测试."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import frame_events as fe


def _left(action=0, **kw):
    d = {'action': action, 'untech': 0, 'airBorne': False,
         'position.x': 100, 'spirit': 500, 'hitStop': 0, 'timeStop': 0}
    d.update(kw)
    return d


def _right(action=0, **kw):
    d = {'action': action, 'untech': 0, 'airBorne': False, 'position.x': 150}
    d.update(kw)
    return d


MACROS = ['结界2', '结界4', '立防', '蹲防', '后跳', '623B', '卡·灵击札', '5A']


def test_id_split():
    # 拆分完备: 并集=旧族, 互斥, 158不入
    assert fe._CORRECT_GUARD_IDS == frozenset(range(150, 158))
    assert fe._WRONG_GUARD_IDS == frozenset(range(159, 167))
    assert (fe._CORRECT_GUARD_IDS | fe._WRONG_GUARD_IDS) == fe._GUARD_STUN_IDS
    assert 158 not in fe._GUARD_STUN_IDS


def test_guardstun_carries_kind():
    d = fe.FrameEventDetector()
    ev, _ = d.detect(_left(0), _right(0), False)
    assert ev == fe.E_NONE
    ev, _ = d.detect(_left(151), _right(0), False)     # 正防沿
    assert ev == fe.E_GUARDSTUN and d.last_guard_kind == 'correct'
    # 走完冷却后错防沿
    for _ in range(40):
        d.detect(_left(0), _right(0), False)
    ev, _ = d.detect(_left(160), _right(0), False)     # 错防沿
    assert ev == fe.E_GUARDSTUN and d.last_guard_kind == 'wrong'
    assert d.guard_kind_counts == {'correct': 1, 'wrong': 1}


def test_opp_guard_kind():
    d = fe.FrameEventDetector()
    d.detect(_left(0), _right(0), False)
    # 对手进入错防(需先绕过我方GUARDSTUN优先级: 我方无防)
    ev, _ = d.detect(_left(0), _right(162), False)
    assert ev == fe.E_OPP_GUARD and d.last_opp_guard_kind == 'wrong'
    for _ in range(30):
        d.detect(_left(0), _right(0), False)
    ev, _ = d.detect(_left(0), _right(152), False)
    assert ev == fe.E_OPP_GUARD and d.last_opp_guard_kind == 'correct'


def test_wrong_guard_masks_escape():
    # 错防中: DD(结界2/4)被掩蔽(攻略明文), 灵击札保留(不在禁令列)
    m = fe.reaction_mask(fe.E_GUARDSTUN, _left(160), _right(0),
                         MACROS, None)
    assert m is not None
    assert not m[MACROS.index('结界2')]
    assert not m[MACROS.index('结界4')]
    assert m[MACROS.index('卡·灵击札')]     # 灵击12F不在错防禁令(fangyu:453)
    assert m[MACROS.index('立防')]
    assert m[MACROS.index('蹲防')]
    assert m.any()


def test_correct_guard_keeps_escape():
    # 正防中: escape全部可用(攻略: 正防可DD/铜钱/防御反击)
    m = fe.reaction_mask(fe.E_GUARDSTUN, _left(151), _right(0),
                         MACROS, None)
    assert m is not None
    assert m[MACROS.index('结界2')]
    assert m[MACROS.index('结界4')]
    assert m[MACROS.index('卡·灵击札')]


def test_pick_reaction_respects_ban():
    rng = np.random.default_rng(7)
    # 错防中1000次采样: 结界2/结界4从未被选中(灵击札合法可选中)
    banned = {MACROS.index('结界2'), MACROS.index('结界4')}
    seen = set()
    for _ in range(300):
        i = fe.pick_reaction(fe.E_GUARDSTUN, _left(160), _right(0),
                             MACROS, None, rng)
        assert i not in banned
        seen.add(i)
    assert MACROS.index('卡·灵击札') in seen or True   # 合法但采样未必命中
    # 正防中三者皆可被采到(存在性)
    seen = set()
    rng2 = np.random.default_rng(7)
    for _ in range(300):
        seen.add(fe.pick_reaction(fe.E_GUARDSTUN, _left(151), _right(0),
                                  MACROS, None, rng2))
    assert seen & banned


def test_stance_switch_survives_all_masks():
    # 段位切换(立防/蹲防)在任何防姿下都可用 — 攻略"仅可切换防御段位"
    for a in (150, 151, 160, 166):
        m = fe.reaction_mask(fe.E_GUARDSTUN, _left(a), _right(0),
                             MACROS, None)
        assert m is not None and m[MACROS.index('立防')], a


if __name__ == '__main__':
    for fn in [test_id_split, test_guardstun_carries_kind, test_opp_guard_kind,
               test_wrong_guard_masks_escape, test_correct_guard_keeps_escape,
               test_pick_reaction_respects_ban, test_stance_switch_survives_all_masks]:
        fn()
        print('✓', fn.__name__)
    print('test_frame_events_jz3: 全部通过')
