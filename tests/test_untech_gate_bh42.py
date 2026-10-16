# -*- coding: utf-8 -*-
"""BH-4.2行为测试(bug_2026-10-15_untech_combo_damage_semantics):
untech语义门 — ①合成: 自由飞翔帧"被锁"位=0/真受击=1 ②事件边沿不因
残留读数伪造 ③combo chain维持仅认真受击 ④R30块/link门同门。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from feat_builder import (FeatureBuilder, HIT_ACT_IDS, eff_untech,
                          GAME_FPS)
from frame_events import (E_AIRTECH, E_COMBO_DROP, E_NONE,
                          FrameEventDetector, FRAME_WINDOWS)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


W = {'id': 0, 'active': 0, 'displayed': None}
BASE_L = {'spirit': 1000, 'position.x': 500.0, 'position.y': 50.0,
          'hp': 10000, 'direction': 1, 'airBorne': False, 'action': 0,
          'cardGauge': 0, 'score': 0, 'hand': b'\xff' * 10,
          'comboDamage': 0, 'untech': 0, 'timeStop': 0, 'hitStop': 0,
          'guardCount': 0}
BASE_R = dict(BASE_L)
BASE_R['direction'] = -1
BASE_R['position.x'] = 700.0


def mk(own_ut=0, own_a=0, opp_ut=0, opp_a=0, opp_air=False):
    l = dict(BASE_L, untech=own_ut, action=own_a)
    r = dict(BASE_R, untech=opp_ut, action=opp_a, airBorne=opp_air)
    return l, r


def core(l, r):
    fb = FeatureBuilder(88)
    return np.asarray(fb.build(l, r, W, []), dtype=np.float32)[:358]


import numpy as np

# 段13擦弹/防守/时间起于257(段1..12账: 16+16+2+14+4+6+36+36+22+75+26+4)
S_OWN_UT, S_OPP_UT = 257 + 5, 257 + 6


def main():
    # ===== ① eff_untech单元: 门矩阵 =====
    for a in (0, 5, 9, 208, 209, 214, 306, 307, 308, 414):
        check('自由行动a=%d残留→0' % a,
              eff_untech({'untech': 30, 'action': a}) == 0)
    for a in sorted(HIT_ACT_IDS)[:6]:
        check('受击族a=%d透传' % a,
              eff_untech({'untech': 30, 'action': a}) == 30)
    check('untech=0受击族→0',
          eff_untech({'untech': 0, 'action': 70}) == 0)
    check('缺字段→0', eff_untech({'action': 70}) == 0)

    # ===== ① 特征层: 双侧untech位(bug档验收口径) =====
    # 对手自由飞翔(214)带残留30F → opp被锁位=0
    l, r = mk(opp_ut=30, opp_a=214, opp_air=True)
    c = core(l, r)
    check('飞翔残留: opp被锁位=0', c[S_OPP_UT] == 0.0)
    # 对手真空中受击(70) 30F → 位=30/62
    l, r = mk(opp_ut=30, opp_a=70, opp_air=True)
    c2 = core(l, r)
    check('真受击: opp被锁位=30/62',
          abs(float(c2[S_OPP_UT]) - min(1.0, 30 / GAME_FPS)) < 1e-6)
    # 我方侧对称
    l, r = mk(own_ut=30, own_a=214)
    c3 = core(l, r)
    check('飞翔残留: own被锁位=0', c3[S_OWN_UT] == 0.0)
    l, r = mk(own_ut=30, own_a=50)
    c4 = core(l, r)
    check('真受击: own被锁位>0', float(c4[S_OWN_UT]) > 0)
    # 布局锚防漂移: 受击位与飞翔位确实在追踪同一维
    check('布局锚一致(同维变化)', c2[S_OPP_UT] != c[S_OPP_UT])

    # ===== ② 事件边沿: 残留读数不伪造COMBO_DROP/AIRTECH =====
    # 对手飞翔残留衰减(30→0, action恒214) → 无COMBO_DROP
    det = FrameEventDetector()
    l, r = mk(opp_ut=30, opp_a=214, opp_air=True)
    det.detect(l, r, False)
    l, r = mk(opp_ut=0, opp_a=214, opp_air=True)
    ev, _ = det.detect(l, r, False)
    check('飞翔残留衰减无COMBO_DROP', ev != E_COMBO_DROP)
    # 真受击恢复(70,30 → 0) + 我方非攻击 → COMBO_DROP
    # (预置last_opp_air=True: 起跳帧会触发E_OPP_JUMP早返回不记untech
    #  基线 — 早返回分支不记last_opp_untech的既有盲点, 与本门无关)
    det = FrameEventDetector()
    det.last_opp_air = True
    l, r = mk(opp_ut=30, opp_a=70, opp_air=True)
    det.detect(l, r, False)
    l, r = mk(opp_ut=0, opp_a=0, opp_air=True)
    ev, _ = det.detect(l, r, False)
    check('真受击恢复触发COMBO_DROP', ev == E_COMBO_DROP)
    # 我方飞翔残留衰减+空中 → 无AIRTECH
    det = FrameEventDetector()
    l, r = mk(own_ut=30, own_a=214)
    l['airBorne'] = True
    det.detect(l, r, False)
    l2, r2 = mk(own_ut=0, own_a=214)
    l2['airBorne'] = True
    ev, _ = det.detect(l2, r2, False)
    check('飞翔残留衰减无AIRTECH', ev != E_AIRTECH)
    # 我方真空中受击恢复+空中 → AIRTECH
    det = FrameEventDetector()
    l, r = mk(own_ut=30, own_a=70)
    l['airBorne'] = True
    det.detect(l, r, False)
    l2, r2 = mk(own_ut=0, own_a=0)
    l2['airBorne'] = True
    ev, _ = det.detect(l2, r2, False)
    check('真空中受击恢复触发AIRTECH', ev == E_AIRTECH)

    # ===== ③ combo chain: 维持仅认真受击(调用方传eff_untech) =====
    fb = FeatureBuilder(88)
    fb.update_combo_chain(500, 30)          # 命中起链
    chain0 = fb._combo_chain
    check('命中起链', chain0 == 1)
    # 真受击维持: 12帧gap全在受击 → 链不断
    for _ in range(12):
        fb.update_combo_chain(0, eff_untech({'untech': 30, 'action': 70}))
    check('真受击链维持', fb._combo_chain == chain0)
    # 自由飞翔(eff=0) 12帧 → 链断(残留读数不再维持)
    for _ in range(12):
        fb.update_combo_chain(0, eff_untech({'untech': 30, 'action': 214}))
    check('自由行动链断(>10帧gap)', fb._combo_chain == 0)

    # ===== ④ comboDamage语义入档断言(dealt非received) =====
    # 特征位[o+3]/[o+4] = left.cd/right.cd原值透传(语义=各自造成的)
    l, r = mk()
    l['comboDamage'], r['comboDamage'] = 1500, 0
    c5 = core(l, r)
    check('comboDamage双侧透传(dealt语义)',
          abs(float(c5[257 + 3]) - 0.5) < 1e-6 and c5[257 + 4] == 0.0)

    # ===== ⑤ 空中被动豁免(BH-4.2抽出可测) =====
    from train_tm import air_passive_exempt
    check('飞翔残留不豁免(被罚)',
          not air_passive_exempt({'airBorne': True, 'action': 214,
                                  'untech': 30}))
    check('真空中受击豁免',
          air_passive_exempt({'airBorne': True, 'action': 70,
                              'untech': 30}))
    check('空中攻击豁免',
          air_passive_exempt({'airBorne': True, 'action': 306,
                              'untech': 0}))
    check('地面无豁免问题(不适用)',
          not air_passive_exempt({'airBorne': False, 'action': 0,
                                  'untech': 0}))

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
