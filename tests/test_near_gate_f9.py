# -*- coding: utf-8 -*-
"""R60-F9行为测试(2026-10-14变异超时补): 330距离门只禁近战子集。

变异面: train_tm距离门`~self.near_idx`→`~self.melee_idx`
(=全攻击集) → 330外弹幕/技能全禁, 远程立回不可学。
钉住: 330外弹幕(5B/5C)必须放行、近战(5A/连段A)必须禁;
150内弹幕禁、近战放行。
"""
import os
import sys
from types import SimpleNamespace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    from train_tm import TMTrainer, CHAR_LIBS
    lib = CHAR_LIBS['reimu']
    names = [m[0] for m in lib['macros']]
    idx = {n: i for i, n in enumerate(names)}
    # 与__init__同源构造(R60-F-9: 近战=melee∪combo∪string)
    _near = (lib.get('melee', set()) | lib.get('combo', set())
             | lib.get('string', set()))
    stub = SimpleNamespace(
        near_idx=np.array([n in _near for n in names], dtype=bool),
        melee_idx=np.array([n in lib['attack'] for n in names],
                           dtype=bool),   # 变异目标(全攻击集)在场
        bullet_idx=np.array([n in lib['bullet'] for n in names],
                            dtype=bool))
    gate = TMTrainer.near_gate.__get__(stub)   # 离线绑定(不启游戏)

    all_on = np.ones(len(names), dtype=bool)

    # 330外: 弹幕放行, 近战禁
    m_far = gate(all_on.copy(), 500.0)
    for nm in ('5B', '5C', '2B'):
        check("330外弹幕放行:%s" % nm, m_far[idx[nm]],
              'near含B?' + str(names[idx[nm]] in _near))
    for nm in ('5A', '连段A'):
        if nm in idx:
            check("330外近战禁:%s" % nm, not m_far[idx[nm]])
    # 150内: 弹幕禁, 近战放行
    m_near = gate(all_on.copy(), 100.0)
    for nm in ('5B', '5C'):
        check("150内弹幕禁:%s" % nm, not m_near[idx[nm]])
    if '5A' in idx and '5A' not in lib['bullet']:
        check("150内近战放行:5A", m_near[idx['5A']])
    # 中距(150-330): 全放行
    m_mid = gate(all_on.copy(), 250.0)
    check("中距全放行", m_mid.all())

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
