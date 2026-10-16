# -*- coding: utf-8 -*-
"""JZ-3.3: E_OPP_JUMP 抓跳事件测试."""
import os
import sys

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


def test_jump_edge_fires():
    d = fe.FrameEventDetector()
    d.detect(_left(0), _right(0), False)
    ev, win = d.detect(_left(0), _right(0, airBorne=True), False)
    assert ev == fe.E_OPP_JUMP
    assert win == 21                       # 大跳被康窗(jump_recovery_windows)
    assert fe.EV_NAMES[fe.E_OPP_JUMP] == 'E_OPP_JUMP'


def test_no_refire_in_air_or_landing():
    d = fe.FrameEventDetector()
    d.detect(_left(0), _right(0), False)
    d.detect(_left(0), _right(0, airBorne=True), False)     # 起跳沿
    ev, _ = d.detect(_left(0), _right(0, airBorne=True), False)  # 空中持续
    assert ev != fe.E_OPP_JUMP
    ev, _ = d.detect(_left(0), _right(0), False)            # 落地
    assert ev != fe.E_OPP_JUMP
    for _ in range(45):                                     # 冷却后二次起跳
        d.detect(_left(0), _right(0), False)
    ev, _ = d.detect(_left(0), _right(0, airBorne=True), False)
    assert ev == fe.E_OPP_JUMP


def test_no_fire_while_i_am_hit_or_attacking():
    d = fe.FrameEventDetector()
    d.detect(_left(0), _right(0), False)
    # 我方受击中(action 50+)不触发(无力反应)
    ev, _ = d.detect(_left(60), _right(0, airBorne=True), False)
    assert ev != fe.E_OPP_JUMP
    d2 = fe.FrameEventDetector()
    d2.detect(_left(0), _right(0), False)
    ev, _ = d2.detect(_left(0), _right(0, airBorne=True), True)  # frozen
    assert ev == fe.E_NONE


def test_reaction_mask_antiair():
    # 黑白: 3A/6A/高跳/前冲/5B/空防 入候选; 无623B(升龙)混入
    names = ['3A', '6A', '高跳', '前冲', '5B', '空防', '623B', '后跳']
    m = fe.reaction_mask(fe.E_OPP_JUMP, _left(0), _right(0, airBorne=True),
                         names, None)
    assert m is not None
    assert m[names.index('3A')] and m[names.index('6A')]
    assert m[names.index('前冲')] and m[names.index('空防')]   # always
    assert not m[names.index('高跳')]        # mid_range: 近距不开放
    assert not m[names.index('5B')]          # far_range: 近距不开放
    assert not m[names.index('623B')]      # 反应表不含升龙(跨库投技陷阱)
    # 距离条件分流: 远距3A关/5B开
    m2 = fe.reaction_mask(fe.E_OPP_JUMP, _left(0),
                          _right(0, airBorne=True, **{'position.x': 800}),
                          names, None)
    assert not m2[names.index('3A')]
    assert m2[names.index('5B')]           # far_range弹幕


def test_suika_lib_no_throw_in_jump_reactions():
    # 真实库: 萃香E_OPP_JUMP候选不含623B(萃鬼投技)
    import train_tm
    names = train_tm.CHAR_LIBS['suika']['names']
    m = fe.reaction_mask(fe.E_OPP_JUMP, _left(0),
                         _right(0, airBorne=True), names, None)
    assert m is not None
    assert not m[names.index('623B')]
    assert m[names.index('3A')]


if __name__ == '__main__':
    for fn in [test_jump_edge_fires, test_no_refire_in_air_or_landing,
               test_no_fire_while_i_am_hit_or_attacking,
               test_reaction_mask_antiair, test_suika_lib_no_throw_in_jump_reactions]:
        fn()
        print('✓', fn.__name__)
    print('test_opp_jump_jz33: 全部通过')
