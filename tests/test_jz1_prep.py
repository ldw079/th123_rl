# -*- coding: utf-8 -*-
"""JZ-1预制件测试: 冷却跟踪/技能摘要/破珠归一/15维填充(离线, 未接线)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jz1_features as j1


def _side(action=0, **kw):
    d = {'action': action, 'airDashCount': 0, 'comboLimit': 0,
         'skills': b'\x00' * 15, 'maxSpirit': 1000, 'hitStop': 0,
         'healingCharm': 0}
    d.update(kw)
    return d


def test_cooldown_classes():
    assert j1.cooldown_frames(400, 0) == 60      # B/C射统一保守
    assert j1.cooldown_frames(432, 0) == 60
    assert j1.cooldown_frames(500, 0) == 120     # 必杀
    assert j1.cooldown_frames(593, 0) == 120
    assert j1.cooldown_frames(300, 0) == 0       # 打击不触发
    assert j1.cooldown_frames(600, 0) == 0       # SC不触发(v1)
    assert j1.cooldown_frames(400, 4) == 48      # 帕秋莉专属
    assert j1.cooldown_frames(500, 4) == 60


def test_cooldown_tracker_window():
    t = j1.SpiritCooldownTracker()
    t.feed(0, 0)                                  # 待机
    assert t.remaining == 0
    t.feed(500, 0)                                # 必杀边沿
    assert t.remaining >= 119                     # 120F刷新后帧首老化
    for _ in range(120):
        t.feed(0, 0)
    assert t.remaining == 0                       # 120F后解锁
    # frozen不推进
    t.feed(400, 0)
    for _ in range(200):
        t.feed(0, 0, frozen=True)
    assert t.remaining > 0
    assert abs(t.value - t.remaining / 120.0) < 1e-9


def test_skills_summary():
    # JZ-0证实: byte4-11=8槽, 0xFF=空, 1/2=等级
    assert j1.skills_summary(b'\x00' * 15) == (0, 0)
    b = bytearray(b'\x00' * 15)
    b[4], b[5], b[6] = 0xFF, 1, 2
    assert j1.skills_summary(bytes(b)) == (2, 2)
    b2 = bytearray(b'\xff' * 15)
    b2[4] = 1
    assert j1.skills_summary(bytes(b2)) == (1, 1)
    assert j1.skills_summary(None) == (0, 0)


def test_orb_broken():
    assert j1.orb_broken_norm(1000) == 0.0        # 满5珠
    assert abs(j1.orb_broken_norm(800) - 1 / 3) < 1e-9
    assert abs(j1.orb_broken_norm(400) - 1.0) < 1e-9   # 破到2珠
    assert j1.orb_broken_norm(0) == 0.0           # 异常值钳零


def test_fill_jz1_15_dims():
    out = np.zeros(20, dtype=np.float32)
    my_cd, opp_cd = j1.SpiritCooldownTracker(), j1.SpiritCooldownTracker()
    my_cd.feed(500, 0)                            # 我方刚必杀
    left = _side(airDashCount=2, comboLimit=80,
                 skills=bytes([0] * 4 + [1, 2, 0xFF] + [0] * 8),
                 maxSpirit=600, healingCharm=1)
    right = _side(action=1, airDashCount=3, comboLimit=40,
                  skills=bytes([0xFF] * 4 + [2, 2, 0xFF, 1] + [0] * 7),
                  maxSpirit=400, hitStop=3)
    n = j1.fill_jz1(out, 3, left, right, my_cd, opp_cd, 0, 1)
    assert n == 15
    seg = out[3:18]
    assert seg[0] > 0 and abs(seg[0] - 2 / 3) < 1e-6     # 我airDash
    assert seg[1] == 1.0                                  # 对手airDash=3
    assert seg[2] > 0.9                                   # 我冷却≈120F
    assert seg[3] == 0.0                                  # 对手无冷却
    assert abs(seg[4] - 0.8) < 1e-6                       # comboLimit
    assert abs(seg[5] - 0.4) < 1e-6
    assert abs(seg[6] - 2 / 4) < 1e-6                     # 我升级数2
    assert abs(seg[7] - 2 / 4) < 1e-6                     # 我最高等级2
    assert abs(seg[8] - 3 / 4) < 1e-6                     # 对手升级数3
    assert abs(seg[9] - 2 / 4) < 1e-6                     # 对手最高2
    assert abs(seg[10] - (5 - 600 / 200) / 3) < 1e-6   # 我600=4珠→破1
    assert abs(seg[11] - 1.0) < 1e-6                      # 对手400=破3
    assert seg[12] == 1.0                                 # 对手蹲姿(action=1)
    assert seg[13] == 1.0                                 # 对手hitStop
    assert seg[14] == 1.0                                 # healingCharm
    assert out[18] == 0.0 and out[19] == 0.0              # 不越界


def test_dim_budget_matches_probe():
    # 探针裁定15维: 2+2+2+4+2+1+1+1
    assert j1.N_DIMS == 15
    assert 343 + j1.N_DIMS == 358


if __name__ == '__main__':
    for fn in [test_cooldown_classes, test_cooldown_tracker_window,
               test_skills_summary, test_orb_broken,
               test_fill_jz1_15_dims, test_dim_budget_matches_probe]:
        fn()
        print('✓', fn.__name__)
    print('test_jz1_prep: 全部通过')
