# -*- coding: utf-8 -*-
"""P1-4(从零#4): 门截断清dec_name → 空挥罚豁免 回归测试。
分支门截断/confirm超时=交还决策权的正常截断, 保留dec_name供W_WHIFF结算;
受击中止/R34/SC中止=真豁免, 继续清名。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from macro_executor import advance_queue


def _left(**kw):
    d = {'action': 0, 'hp': 10000, 'spirit': 1000, 'position.x': 500,
         'hitStop': 0, 'untech': 0}
    d.update(kw)
    return d


def _right(**kw):
    d = {'action': 0, 'hp': 10000, 'position.x': 700, 'untech': 0}
    d.update(kw)
    return d


def _noop():
    pass


def test_branch_truncation_keeps_name():
    """分支门无匹配路由(whiff默认) → 队清但名保留。"""
    q = [('branch', {'hit': [(('A',), 3)], 'blocked': [(('B',), 3)],
                     'opp_jump': None, 'whiff': None}),
         (('A',), 5)]
    q2, _g, name, _inp = advance_queue(
        q, 0, _left(), _right(), 0.0, 0.0, False, 1000, 200,
        '连段B', set(), set(), _noop, _noop)
    assert q2 == [], '队列应清'
    assert name == '连段B', '分支门截断应保留dec_name(空挥可结算): %r' % name


def test_confirm_timeout_keeps_name():
    """confirm门4帧无命中且非cconfirm近距 → 截断保名。"""
    q = [('confirm', 4)]
    q2, g, name, _inp = advance_queue(
        q, 0, _left(), _right(**{'position.x': 900}), 0.0, 0.0, False, 1000,
        200, '5A确认', set(), set(), _noop, _noop)
    # gate_frames逐帧+1, 推到≥4超时
    for _ in range(4):
        q2, g, name, _inp = advance_queue(
            q2, g, _left(), _right(**{'position.x': 900}), 0.0, 0.0, False,
            1000, 200, name, set(), set(), _noop, _noop)
    assert q2 == [], '超时应清队'
    assert name == '5A确认', 'confirm超时应保留dec_name: %r' % name


def test_hit_interrupt_still_clears():
    """受击中止=真豁免, 清名不变(P2-1语义)。"""
    q = [(('A',), 10)]
    q2, _g, name, _inp = advance_queue(
        q, 0, _left(hp=9000), _right(), 0.0, 200.0, False, 1000, 200,
        '5A', set(), set(), _noop, _noop)
    assert q2 == [] and name is None, '受击中止应清名(豁免)'


def test_r34_interrupt_still_clears():
    """R34中断(对手攻击+近距+我方可动)=豁免, 清名不变。"""
    q = [(('A',), 10)]
    q2, _g, name, _inp = advance_queue(
        q, 0, _left(action=4), _right(action=310), 0.0, 0.0, False,
        1000, 100, '5A', set(), set(), _noop, _noop)
    assert q2 == [] and name is None, 'R34中断应清名(豁免)'


if __name__ == '__main__':
    for fn in [test_branch_truncation_keeps_name,
               test_confirm_timeout_keeps_name,
               test_hit_interrupt_still_clears,
               test_r34_interrupt_still_clears]:
        fn()
        print('✓', fn.__name__)
    print('test_decname_whiff_p1: 全部通过')
