# -*- coding: utf-8 -*-
"""R61z行为测试: 进攻积极性奖励(距离势差+空中被动惩罚)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from train_tm import (state_potential, POT_W, R_AIR_PASSIVE,
                       AIR_PASSIVE_GRACE)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def st(my_x=500, opp_x=600, my_air=False, my_a=0, untech=0):
    return (
        {"hp": 10000, "spirit": 1000, "position.x": my_x,
         "airBorne": my_air, "action": my_a, "untech": untech,
         "cardGauge": 0},
        {"hp": 10000, "position.x": opp_x, "airBorne": False,
         "action": 0},
    )


def main():
    # ===== 距离势差 =====
    # 1. 贴近势高
    l, r = st(my_x=500, opp_x=550)   # dx=50
    p_close = state_potential(l, r)
    l, r = st(my_x=500, opp_x=800)   # dx=300
    p_mid = state_potential(l, r)
    l, r = st(my_x=500, opp_x=1200)  # dx=700
    p_far = state_potential(l, r)
    check('贴近>中距', p_close > p_mid)
    check('中距>远距', p_mid > p_far)
    check('远距势=0(无engage)', p_far >= 0)

    # 2. 势差量级合理
    engage_close = POT_W['engage'] * 5.5   # (600-50)/100=5.5
    engage_far = 0                          # 700>600 → 0
    actual_diff = p_close - p_far
    expected_diff = engage_close - engage_far
    check('势差量级', abs(actual_diff - expected_diff) < 0.01,
          'Δ=%.3f 预期=%.3f' % (actual_diff, expected_diff))

    # 3. 100px前进→正差(奖励)
    l, r = st(my_x=500, opp_x=350)   # dx=150
    p1 = state_potential(l, r)
    l, r = st(my_x=500, opp_x=250)   # dx=250 (对手后退100px)
    p2 = state_potential(l, r)
    check('100px接近→势升', p1 > p2, 'Δ=%.3f' % (p1 - p2))

    # 4. 往返=净零(telescoping)
    l, r = st(my_x=500, opp_x=350)
    p_start = state_potential(l, r)
    l, r = st(my_x=500, opp_x=550)   # 退200
    p_retreat = state_potential(l, r)
    l, r = st(my_x=500, opp_x=350)   # 进200(回到原位)
    p_return = state_potential(l, r)
    check('往返净差≈0', abs(p_return - p_start) < 1e-6)

    # ===== 空中被动参数 =====
    # 5. 常量在位
    check('R_AIR_PASSIVE=0.003', R_AIR_PASSIVE == 0.003)
    check('宽限30帧', AIR_PASSIVE_GRACE == 30)
    check('engage权重', POT_W.get('engage', 0) > 0)

    # 6. 60帧跳的代价
    # 60帧空中 - 30帧宽限 = 30帧惩罚 × 0.003 = -0.09
    cost = max(0, 60 - AIR_PASSIVE_GRACE) * R_AIR_PASSIVE
    check('60帧跳≈-0.09', abs(cost - 0.09) < 0.01, '%.3f' % cost)

    # 7. 势函数不含跳跃直接惩罚(空中被动是事件奖励不是势函数项)
    l_air, r = st(my_x=500, opp_x=550, my_air=True)
    l_ground, _ = st(my_x=500, opp_x=550, my_air=False)
    check('势函数不看airBorne',
          abs(state_potential(l_air, r)
              - state_potential(l_ground, r)) < 1e-6)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
