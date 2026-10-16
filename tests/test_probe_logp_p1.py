# -*- coding: utf-8 -*-
"""P1-5(从零#4): 探针决策stored_logp混合分布测试 —
行为边际=0.7·(0.12·U+0.88·π)+0.3·1{vg_best}, 纯π记录系有偏(~40%决策)."""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from train_tm import mixed_behavior_p


def test_pure_pi_passthrough():
    # 无探针无VG: 原样(钳下限)
    assert mixed_behavior_p(0.5, 3) == 0.5
    assert mixed_behavior_p(0.0, 3) == 1e-10


def test_probe_mixture():
    # 探针10宏: mid在legal → 0.88π + 0.012; 不在legal → 0.88π
    legal = list(range(10))
    p_in = mixed_behavior_p(0.5, 3, probe_legal=legal)
    assert abs(p_in - (0.88 * 0.5 + 0.12 / 10)) < 1e-12
    p_out = mixed_behavior_p(0.5, 50, probe_legal=legal)
    assert abs(p_out - 0.88 * 0.5) < 1e-12


def test_vg_mixture():
    # VG on: mid==best → 0.7π+0.3; 否则 0.7π
    assert abs(mixed_behavior_p(0.4, 7, vg_on=True, vg_best=7)
               - (0.7 * 0.4 + 0.3)) < 1e-12
    assert abs(mixed_behavior_p(0.4, 8, vg_on=True, vg_best=7)
               - 0.7 * 0.4) < 1e-12


def test_full_mixture():
    # 探针+VG全开: P=0.7·(0.12U+0.88π)+0.3·1{best}
    legal = [0, 1, 2]
    p = mixed_behavior_p(0.2, 1, probe_legal=legal, vg_on=True, vg_best=1)
    inner = 0.12 / 3 + 0.88 * 0.2
    assert abs(p - (0.7 * inner + 0.3)) < 1e-12
    p2 = mixed_behavior_p(0.2, 2, probe_legal=legal, vg_on=True, vg_best=1)
    inner2 = 0.12 / 3 + 0.88 * 0.2   # 2在legal内
    assert abs(p2 - 0.7 * inner2) < 1e-12


def test_bias_direction():
    # 有偏性修复方向: 探针选中低π宏时, 混合logp > 纯πlogp(否则ratio爆炸)
    import math
    p = mixed_behavior_p(0.001, 0, probe_legal=[0, 1])
    assert p > 0.001                     # 均匀成分垫底
    assert math.log(p) > math.log(0.001)


if __name__ == '__main__':
    for fn in [test_pure_pi_passthrough, test_probe_mixture,
               test_vg_mixture, test_full_mixture, test_bias_direction]:
        fn()
        print('✓', fn.__name__)
    print('test_probe_logp_p1: 全部通过')
