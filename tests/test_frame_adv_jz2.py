# -*- coding: utf-8 -*-
"""JZ-2: frame_adv 表驱动帧差函数测试 (攻略算例回归锚)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import frame_adv as fa


def test_tables_match_guide():
    # 数值表=CHM图片视觉转录, 与system.txt行内文字双源一致
    assert fa.LEVELS == ['小', '中', '大', '特大']
    assert fa.AIR_GUARD == 19
    assert [fa.hit_stun(l) for l in fa.LEVELS] == [10, 17, 24, 34]
    assert [fa.guard_stun(l) for l in fa.LEVELS] == [9, 15, 21, 27]
    assert [fa.guard_stun(l, correct=False) for l in fa.LEVELS] == [11, 19, 27, 31]


def test_suika_near_a_anchor():
    # 萃香近A: 等级中/发生9/终了26 (综合攻略line 1241-1253自测吻合)
    assert fa.frame_advantage(26, 9, '中', correct=True) == -2
    assert fa.frame_advantage(26, 9, '中', correct=False) == 2


def test_counter_upgrade():
    assert fa.hit_stun('中', counter=True) == fa.hit_stun('大')
    assert fa.hit_stun('特大', counter=True) == fa.hit_stun('特大')  # 顶格


def test_guard_no_counter():
    # COUNTER是命中概念: 打防场景显式拒绝, 防止误用
    try:
        fa.frame_advantage(26, 9, '中', counter=True)
        raise AssertionError('应拒绝counter打防')
    except ValueError:
        pass


def test_yukari_utsuho_examples():
    # 综合攻略outline_74: 紫妈6A(大/发生15/终了40)打防-4F, 3A(大/13/45)-11F
    # 高达6A(大/13/39)-5F, 3A(大/12/50)-17F
    assert fa.frame_advantage(40, 15, '大') == -4
    assert fa.frame_advantage(45, 13, '大') == -11
    assert fa.frame_advantage(39, 13, '大') == -5
    assert fa.frame_advantage(50, 12, '大') == -17


if __name__ == '__main__':
    for fn in [test_tables_match_guide, test_suika_near_a_anchor,
               test_counter_upgrade, test_guard_no_counter,
               test_yukari_utsuho_examples]:
        fn()
        print('✓', fn.__name__)
    print('test_frame_adv_jz2: 全部通过')
