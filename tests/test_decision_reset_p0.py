# -*- coding: utf-8 -*-
"""P0(从零#4): note_decision吞并局级重置块回归测试 —
决策点(≈每10帧)不得清局级状态; reset_match才清。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import numpy as np
from feat_builder import FeatureBuilder


def test_decision_keeps_match_state():
    fb = FeatureBuilder(n_macros=22)
    # 局内累积状态(原被note_decision错杀的族)
    fb._skill_levels = [2, 1, 0, 3]
    fb._opp_hand_prev = b'\x01\x02'
    fb._opp_revealed_skill[3] = 2.0
    fb._opp_revealed_sc = 1
    fb._own_vx_m, fb._dx_m, fb._adx_m = 3.5, -1.2, 4.5
    fb._own_air_f = 7
    fb._combo_chain = 4
    fb._chain_gap = 2
    fb._opp_vx_ema = -6.0
    for _ in range(5):                    # 5个决策点(≈50帧)
        fb.note_decision(1)
    assert fb._skill_levels == [2, 1, 0, 3], '技能等级被决策点清零'
    assert fb._opp_hand_prev == b'\x01\x02'
    assert fb._opp_revealed_skill[3] == 2.0
    assert fb._opp_revealed_sc == 1
    assert fb._own_vx_m == 3.5 and fb._adx_m == 4.5
    assert fb._own_air_f == 7
    assert fb._combo_chain == 4 and fb._chain_gap == 2
    assert fb._opp_vx_ema == -6.0, '对手速度EMA被决策点清零'
    # 决策序列自身仍工作
    assert fb._dec_hist == [1] * 5


def test_reset_match_clears_state():
    fb = FeatureBuilder(n_macros=22)
    fb._skill_levels = [2, 1, 0, 3]
    fb._opp_revealed_sc = 1
    fb._own_vx_m = 3.5
    fb._combo_chain = 4
    fb._dec_hist = [1, 2, 3]
    fb.reset_match()
    assert fb._skill_levels == [0, 0, 0, 0]
    assert fb._opp_revealed_sc == 0
    assert fb._own_vx_m == 0.0
    assert fb._combo_chain == 0
    assert fb._dec_hist == []            # 决策序列局内重置(S-2语义)


def test_skill_dim_alive_across_decisions():
    """动态探针(分片A复现口径): 技能升级后跨两次决策, 维230仍非零。"""
    fb = FeatureBuilder(n_macros=22)
    fb.reset_match()
    fb._char_name = 'reimu'

    def _pkt(i):
        left = {"position.x": 300.0, "position.y": 50.0, "spirit": 1000,
                "hp": 10000, "airBorne": False, "direction": 1,
                "action": 0, "cardGauge": 0, "score": 0,
                "hand": b"\xff" * 10, "comboDamage": 0, "untech": 0,
                "timeStop": 0, "hitStop": 0}
        right = dict(left)
        right["position.x"] = 900.0
        right["action"] = 0
        weather = {"active": 0, "displayed": 0, "timer": 0}
        return left, right, weather, []

    # 技能升到Lv2(直接设内部态 — 升级路径的adjust_script另测)
    fb._skill_levels = [2, 0, 0, 0]
    v0 = np.asarray(fb.build(*_pkt(0)), dtype=np.float64)
    assert v0[230] > 0, '维230(技能Lv)本底就死'
    fb.note_decision(1)
    v1 = np.asarray(fb.build(*_pkt(1)), dtype=np.float64)
    fb.note_decision(2)
    v2 = np.asarray(fb.build(*_pkt(2)), dtype=np.float64)
    assert v1[230] > 0 and v2[230] > 0, \
        '两次决策后技能维被清零(P0回归): %.3f %.3f' % (v1[230], v2[230])
    # 局重置后归零
    fb.reset_match()
    v3 = np.asarray(fb.build(*_pkt(3)), dtype=np.float64)
    assert v3[230] == 0.0


if __name__ == '__main__':
    for fn in [test_decision_keeps_match_state, test_reset_match_clears_state,
               test_skill_dim_alive_across_decisions]:
        fn()
        print('✓', fn.__name__)
    print('test_decision_reset_p0: 全部通过')
