# -*- coding: utf-8 -*-
"""JZ-3.2: 投技合法性门测试 — ThrowInvulnTracker四窗口 + 掩码门."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frame_events import ThrowInvulnTracker


def _opp(action=0, **kw):
    d = {'action': action, 'untech': 0, 'airBorne': False,
         'position.x': 200, 'position.y': 0}
    d.update(kw)
    return d


def test_wakeup_window():
    t = ThrowInvulnTracker()
    t.feed(_opp(97))                       # 倒地静止
    t.feed(_opp(0))                        # 起身瞬间
    assert t.invuln > 0                    # 10F无敌开始
    frames = 0
    while t.invuln > 0 and frames < 30:
        t.feed(_opp(0))
        frames += 1
    assert 8 <= frames <= 11, frames       # ≈10F(计数语义)
    t.feed(_opp(0))
    assert t.invuln == 0                   # 窗口结束


def test_guardstun_window():
    t = ThrowInvulnTracker()
    t.feed(_opp(151))                      # 正防硬直中
    assert t.invuln > 0
    t.feed(_opp(151))
    t.feed(_opp(0))                        # 出防
    assert t.invuln > 0                    # 出防后仍无敌10F
    n = 0
    while t.invuln > 0 and n < 30:
        t.feed(_opp(0))
        n += 1
    assert 8 <= n <= 11, n
    assert t.invuln == 0


def test_jump_1f_window():
    t = ThrowInvulnTracker()
    t.feed(_opp(0))
    t.feed(_opp(0, airBorne=True))         # 离地瞬间
    assert t.invuln > 0                    # 1F
    t.feed(_opp(0, airBorne=True))
    assert t.invuln == 0                   # 窗口极短


def test_untech_float():
    # BH-4.2: untech过动作门 — 浮空受身标记仅认真受击(action∈受击族;
    # 原60∉HIT_ACT_IDS为无效ID, 用70=空中受击)
    t = ThrowInvulnTracker()
    t.feed(_opp(70, airBorne=True, untech=30))   # 浮空受身不可
    assert t.invuln > 0
    t.feed(_opp(70, airBorne=True, untech=1))
    assert t.invuln > 0
    t.feed(_opp(70, airBorne=True, untech=0))    # 可受身=仍按浮空近1F
    t.feed(_opp(0))
    assert t.invuln == 0
    # 自由飞翔的残留untech不标记投技无敌
    # (先喂一帧离地: 离地1F窗是JUMP_F路径, 与untech路径无关)
    t2 = ThrowInvulnTracker()
    t2.feed(_opp(214, airBorne=True, untech=0))
    t2.feed(_opp(214, airBorne=True, untech=30))
    assert t2.invuln == 0


def test_frozen_no_advance():
    t = ThrowInvulnTracker()
    t.feed(_opp(97))
    t.feed(_opp(0))                        # 起身, invuln≈9
    for _ in range(50):
        t.feed(_opp(0), frozen=True)       # hitstop中不推进
    assert t.invuln > 0


def test_mask_gate_simulated():
    # 模拟决策门: 无敌窗内投技被禁, 窗外恢复
    names = ['5A', '择·投', '623B', '立防']
    throw_idx = np.array([n in {'择·投', '623B'} for n in names])
    base = np.array([True, True, True, True])
    t = ThrowInvulnTracker()
    t.feed(_opp(160))                      # 错防中
    mask = base & ~throw_idx if t.invuln > 0 else base
    assert not mask[1] and not mask[2] and mask[0] and mask[3]
    for _ in range(20):
        t.feed(_opp(0))
    assert t.invuln == 0
    mask = base & ~throw_idx if t.invuln > 0 else base
    assert mask[1] and mask[2]


def test_throw_sets_registered():
    # CHAR_LIBS throw集合接线(不启动游戏, 只装载)
    import train_tm
    for ch, expect in (('reimu', {'择·投'}), ('marisa', {'择·投'}),
                       ('suika', {'择·投', '623B'})):
        lib = train_tm.CHAR_LIBS[ch]
        assert lib.get('throw') == expect, (ch, lib.get('throw'))
        names = lib['names']
        idx = [i for i, n in enumerate(names) if n in lib['throw']]
        assert idx, ch                  # 宏库中真实存在投技宏


if __name__ == '__main__':
    for fn in [test_wakeup_window, test_guardstun_window, test_jump_1f_window,
               test_untech_float, test_frozen_no_advance,
               test_mask_gate_simulated, test_throw_sets_registered]:
        fn()
        print('✓', fn.__name__)
    print('test_throw_gate_jz3: 全部通过')
