# -*- coding: utf-8 -*-
"""B(用户2026-10-07"开工B"): 行为风格估计器行为测试。
对手已出卡差分→风格特征段(316..329)。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from feat_builder import FeatureBuilder  # noqa

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def fb():
    return FeatureBuilder(6)


def own(x=500.0, spirit=1000.0):
    return {"position.x": x, "position.y": 0.0, "direction": 1,
            "action": 0, "spirit": spirit, "hp": 10000,
            "airBorne": False, "untech": 0, "cardGauge": 0,
            "score": 0, "comboDamage": 0, "hitStop": 0, "timeStop": 0,
            "hand": b'\xff' * 10, "pose": 0, "poseFrame": 0}


def opp(x=700.0, hand=None):
    h = hand if hand is not None else b'\xff' * 10
    return {"position.x": x, "position.y": 0.0, "direction": -1,
            "action": 0, "spirit": 1000.0, "hp": 10000,
            "airBorne": False, "untech": 0, "cardGauge": 0,
            "score": 0, "comboDamage": 0, "hitStop": 0, "timeStop": 0,
            "hand": h, "pose": 0, "poseFrame": 0}


W = {"active": 0}


def hand5(*ids):
    """构造5槽手牌bytes(id→id+0x00; 空槽0xFF)."""
    out = bytearray(b'\xff' * 10)
    for i, cid in enumerate(ids[:5]):
        out[i * 2] = cid
        out[i * 2 + 1] = 0
    return bytes(out)


def main():
    # 1. CORE_DIMS=330
    check('CORE_DIMS=330', FeatureBuilder.CORE_DIMS == 330)

    f = fb()
    check('n_side含B段', f.n_side == 2 * 6 + 330)

    # 2. 初始状态: 风格段全零
    l, r = own(), opp()
    f.update_opp(0.1, l, r, W)
    core = f.build(l, r, W, [])
    check('初始风格段全零', all(core[316 + i] == 0.0
                              for i in range(14)))

    # 3. 对手打出技能卡100 → 槽位0=1
    f2 = fb()
    h0 = hand5(100, 201, 5, 0xFF)      # 3张: 技能100+SC201+系统5
    l, r = own(), opp(hand=h0)
    f2.update_opp(0.1, l, r, W)          # 建立基线
    h1 = hand5(0xFF, 0xFF, 5, 0xFF)     # 消失: 100和201(使用)
    r2 = opp(hand=h1)
    f2.update_opp(0.1, l, r2, W)
    core = f2.build(l, r2, W, [])
    check('技能100→槽位0', core[316] == 1.0)
    check('SC201→SC计数1/5', abs(core[328] - 0.2) < 1e-6)
    check('系统5未消失→sys=0', core[329] == 0.0)
    check('其余槽位=0', all(core[316 + i] == 0.0
                           for i in range(1, 12)))

    # 4. 晴岚遮蔽→差分跳过
    f3 = fb()
    l, r = own(), opp(hand=hand5(100))
    f3.update_opp(0.1, l, r, W)
    ws = {"active": 11}                  # 晴岚
    r3 = opp(hand=b'\xff' * 10)
    f3.update_opp(0.1, l, r3, ws)
    core = f3.build(l, r3, ws, [])
    check('晴岚期不差分', core[316] == 0.0)

    # 5. 跨局清零
    f3.reset_match()
    check('reset清零风格', f3._opp_revealed_skill[0] == 0.0
          and f3._opp_revealed_sc == 0)

    # 6. 多卡消失
    f4 = fb()
    l, r = own(), opp(hand=hand5(100, 101, 102, 103, 104))
    f4.update_opp(0.1, l, r, W)
    r4 = opp(hand=hand5(0xFF, 0xFF, 0xFF, 0xFF, 0xFF))
    f4.update_opp(0.1, l, r4, W)
    core = f4.build(l, r4, W, [])
    check('5技能全出→5槽位=1', sum(core[316 + i]
                                  for i in range(12)) == 5.0)

    # 7. load迁移: 旧316模型→新330侧(net自动插零)
    from ppo import PPOTrainer
    import tempfile
    tmp = tempfile.mkdtemp(prefix='b_test_')
    old_t = PPOTrainer(n_side=5 * 6 + 316, n_out=6)
    old_t.init_fresh(14400)
    old_pi = os.path.join(tmp, 'old.npz')
    old_v = os.path.join(tmp, 'old_v.npz')
    old_t.save(old_pi, old_v)
    new_t = PPOTrainer(n_side=5 * 6 + 330, n_out=6)
    new_t.load(old_pi, old_v)
    check('load旧模型→新宽', new_t.W_side.shape[0] == 5 * 6 + 330)

    # 8. 旧策略保持: 用旧模型前向(取前316维=旧布局)与新模型
    #    前316位权重相同→旧策略逐位不变(B段零权重=零贡献)
    check('旧core权重保持', np.allclose(
        new_t.W_side[:2 * 6 + 316], old_t.W_side[:2 * 6 + 316]))

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
