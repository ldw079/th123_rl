# -*- coding: utf-8 -*-
"""A1-1(未决问题方案§A) 配对测试: passivity_meter 被动性仪表.

覆盖:
  1. **列号经feat_builder标定**(R67c教训: B3曾断言与实现同错读列 —
     adx列必须从独立源钉死, 符号消歧dx/adx双解)
  2. 远弹份额分母=远程桶决策(近战弹幕不入远程分母)
  3. 逼近率: adx递减占比
  4. 开局攻击率: 前8拍攻击族
  5. 汇总行数值
"""
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from passivity_meter import (ADX_COL, OPENING_DECISIONS, episode_passivity,
                             passivity_line)

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def build_core(lx, rx):
    """feat_builder真构建(独立于passivity_meter的列常量)."""
    from feat_builder import FeatureBuilder
    mk = dict(action=0, airBorne=0, cardGauge=0xFFFF, comboDamage=0,
              direction=1, hand=[0xFF] * 10, hitStop=0, hp=10000, score=0,
              spirit=1000, timeStop=0, untech=0)
    L = dict(mk, **{"position.x": lx, "position.y": 0.0})
    R = dict(mk, **{"position.x": rx, "position.y": 0.0})
    return FeatureBuilder(4).build(
        L, R, {"id": 0, "active": 0, "displayed": 0}, [])


def main():
    # --- 1. 列号标定(符号消歧) ---
    core = build_core(580.0, 100.0)   # dx=-480, adx=+480
    hits = [i for i in range(16) if abs(float(core[i]) * 600.0 - 480.0) < 1.0]
    ok(hits == [ADX_COL], "adx列经feat_builder标定=col%d(符号消歧)" % ADX_COL)

    # --- 2-4. 合成episode ---
    from train_tm import CHAR_LIBS
    char = 'reimu'
    names = CHAR_LIBS[char]['names']
    n_macros = len(names)
    b_ids = [i for i, nm in enumerate(names) if nm in CHAR_LIBS[char]['bullet']]
    atk_ids = [i for i, nm in enumerate(names)
               if nm in CHAR_LIBS[char]['attack']]
    nb = [i for i in range(n_macros)
          if i not in set(b_ids) | set(atk_ids)][0]

    def mk_ep(adx_rows, act_ids):
        n = len(act_ids)
        sides = np.zeros((n, 5 * n_macros + 330), dtype=np.float32)
        sides[:, 2 * n_macros + ADX_COL] = np.clip(
            np.array(adx_rows) / 600.0, 0, 1)
        return {'acts': np.array(act_ids, dtype=np.int64), 'sides': sides}

    # 8拍: 前4近(200px, 非攻击)后4远(450px, 弹幕/非弹幕各2) — 开局攻=前8拍含弹幕2/8? 弹幕∈attack集
    ep = mk_ep([200] * 4 + [450] * 4, [nb] * 4 + [b_ids[0], nb, b_ids[0], nb])
    fs, fn, cl, op = episode_passivity(char, ep)
    ok(abs(fs - 0.5) < 1e-9 and fn == 4,
       "远弹份额=0.5(分母=远程4拍, 近战弹幕不入)")
    ok(abs(op - 2.0 / 8.0) < 1e-9, "开局攻击率=2/8(弹幕∈attack族)")

    ep2 = mk_ep([500, 400, 300, 500], [nb] * 4)
    _fs2, _fn2, cl2, _op2 = episode_passivity(char, ep2)
    ok(abs(cl2 - 0.6666666666666666) < 1e-9,
       "逼近率=2/3(降-降-升)")

    # --- 5. 汇总行 ---
    line = passivity_line([(0.5, 4, 0.5, 0.25), (None, 0, 1.0, 0.5)])
    ok(line == '远弹50%(n4) 逼近75% 开局攻38%',
       "汇总行数值(%s)" % line)

    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
