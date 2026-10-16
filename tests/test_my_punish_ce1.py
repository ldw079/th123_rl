# -*- coding: utf-8 -*-
"""CE-1: MyPunishTracker宏层(招式级反制画像)测试 — 双层结构+分层回退。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from my_punish_tracker import (MyPunishTracker, CLASSES,
                               PUNISHED, LANDED, WHIFFED)


def test_backward_compat():
    """不传name时行为与原版完全一致(宏层不启动)。"""
    t = MyPunishTracker()
    t.begin('JUMP')
    t.frame(100, True, 0)
    t.end()
    assert t.rate['JUMP'] > 0
    assert t.macro_rate == {}       # 宏层未启用
    assert t.macro_n == {}


def test_macro_layer_basic():
    """传name时宏层记录独立EMA。"""
    t = MyPunishTracker()
    t.begin('JUMP', name='跳跃')
    t.frame(100, True, 0)
    assert t.end() == PUNISHED
    assert '跳跃' in t.macro_rate
    assert t.macro_rate['跳跃'] > 0
    assert t.macro_n['跳跃'] == 1

    t.begin('JUMP', name='高跳')
    t.frame(0, False, 200)
    assert t.end() == LANDED
    assert '高跳' in t.macro_rate
    # 高跳被记为LANDED→rate仍0(只有PUNISHED才升)
    assert t.macro_rate['高跳'] == 0.0


def test_macro_independence():
    """不同宏名独立跟踪(5B被反制不影响5A)。"""
    t = MyPunishTracker(alpha=0.3, macro_alpha=0.5)
    # 5B连续被反制
    for _ in range(5):
        t.begin('BULLET', name='5B')
        t.frame(100, True, 0)
        t.end()
    # 5A安全命中
    for _ in range(3):
        t.begin('MELEE', name='5A')
        t.frame(0, False, 200)
        t.end()
    assert t.macro_rate['5B'] > 0.5
    assert t.macro_rate['5A'] == 0.0


def test_layered_fallback():
    """宏层样本<min_n时回退到类别率。"""
    t = MyPunishTracker()
    # 类别层: JUMP被反制3次
    for _ in range(3):
        t.begin('JUMP')
        t.frame(100, True, 0)
        t.end()
    cat_rate = t.rate['JUMP']
    assert cat_rate > 0

    # 宏层: '跳跃'只有1次(低于min_n=3) → 回退到类别率
    t.begin('JUMP', name='跳跃')
    t.frame(0, False, 200)
    t.end()
    assert t.macro_n['跳跃'] == 1
    # 回退: macro_punish_rate应返回**当前**类别率(已被第4次调用更新)
    assert abs(t.macro_punish_rate('跳跃', cls='JUMP') - t.rate['JUMP']) < 1e-9

    # 宏层够样本后用自身率
    for _ in range(5):
        t.begin('JUMP', name='跳跃')
        t.frame(0, False, 200)
        t.end()
    assert t.macro_n['跳跃'] == 6   # 1+5
    # 自身全是LANDED→rate降到0(不再回退)
    assert t.macro_punish_rate('跳跃', cls='JUMP') < cat_rate


def test_unknown_macro():
    """未见过的宏→类别率或0。"""
    t = MyPunishTracker()
    t.begin('BULLET', name='5B')
    t.frame(100, True, 0)
    t.end()
    # 有类别上下文
    assert t.macro_punish_rate('从未用过的招', cls='BULLET') == \
        t.rate['BULLET']
    # 无类别上下文
    assert t.macro_punish_rate('从未用过的招') == 0.0


def test_slow_ema():
    """宏层EMA比类别层慢(macro_alpha=0.1 vs alpha=0.3)。"""
    t = MyPunishTracker()
    for _ in range(3):
        t.begin('JUMP', name='跳跃')
        t.frame(100, True, 0)
        t.end()
    # 类别层3次后应显著>宏层(快EMA)
    assert t.rate['JUMP'] > t.macro_rate['跳跃']
    # 10次后宏层也显著(慢但收敛)
    for _ in range(10):
        t.begin('JUMP', name='跳跃')
        t.frame(100, True, 0)
        t.end()
    assert t.macro_rate['跳跃'] > 0.4


def test_macro_snapshot():
    """宏层快照只返回n≥3的宏。"""
    t = MyPunishTracker()
    # '5B' 5次
    for _ in range(5):
        t.begin('BULLET', name='5B')
        t.frame(100, True, 0)
        t.end()
    # '6B' 1次(不进快照)
    t.begin('BULLET', name='6B')
    t.frame(100, True, 0)
    t.end()
    snap = t.macro_snapshot()
    assert '5B' in snap
    assert '6B' not in snap


def test_train_tm_integration():
    """train_tm已有调用点不受影响(begin(cls)仍有效)。"""
    t = MyPunishTracker()
    # 模拟train_tm的调用模式
    t.begin('MELEE')
    for i in range(10):
        t.frame(0, False, 100 if i == 5 else 0)
    result = t.end()
    assert result == LANDED
    assert t.rate['MELEE'] == 0.0     # 未被punish


if __name__ == '__main__':
    for fn in [test_backward_compat, test_macro_layer_basic,
               test_macro_independence, test_layered_fallback,
               test_unknown_macro, test_slow_ema, test_macro_snapshot,
               test_train_tm_integration]:
        fn()
        print('✓', fn.__name__)
    print('test_my_punish_ce1: 全部通过')
