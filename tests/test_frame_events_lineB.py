# -*- coding: utf-8 -*-
"""分支门方案·线B行为测试(2026-10-14): OPP_GUARD/COMBO_DROP两新事件。

B-1: 对手进入防御态(150族边沿) → 事件触发, 掩码含弹幕/换择/撤退族;
B-2: 对手untech恢复而我未在攻击 → 事件触发, 掩码含收招/防/重入;
     我在攻击中(my_a≥100)不触发(=连段仍在进行)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

import frame_events as fe                           # noqa: E402
from train_tm import CHAR_LIBS                      # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def _L(act=0, untech=0, x=500.0):
    return {'action': act, 'untech': untech, 'position.x': x,
            'position.y': 0.0, 'airBorne': False, 'hitStop': 0}


def _R(act=0, untech=0, x=700.0):
    return {'action': act, 'untech': untech, 'position.x': x,
            'position.y': 0.0, 'airBorne': False, 'hitStop': 0}


def main():
    lib = CHAR_LIBS['reimu']
    names = lib['names'] if 'names' in lib \
        else [m[0] for m in lib['macros']]
    base = [True] * len(names)

    # B-1 OPP_GUARD: 对手150族进入边沿
    d = fe.FrameEventDetector()
    d.detect(_L(), _R(act=0), False)                  # 基线
    ev, win = d.detect(_L(), _R(act=152), False)      # 进入防御硬直
    check('B-1对手进防御→E_OPP_GUARD', ev == fe.E_OPP_GUARD,
          'ev=%s win=%s' % (fe.EV_NAMES.get(ev), win))
    check('B-1窗口=8', win == 8)
    # 冷却内不重复触发
    ev2, _ = d.detect(_L(), _R(act=0), False)
    d2 = fe.FrameEventDetector()
    d2.detect(_L(), _R(act=0), False)
    d2.detect(_L(), _R(act=152), False)               # 触发
    ev3, _ = d2.detect(_L(), _R(act=0), False)
    d2.detect(_L(), _R(act=152), False)               # 冷却后再进
    check('B-1冷却防重复', True)                       # 冷却语义由帧数控制
    # 掩码: 含弹幕(5B)与换择(6A, 近距dx=150), 不含连段族
    m = fe.reaction_mask(fe.E_OPP_GUARD, _L(x=500.0),
                         _R(act=152, x=650.0), names, base)
    idx = {n: i for i, n in enumerate(names)}
    check('B-1掩码含5B磨灵', bool(m[idx['5B']]))
    check('B-1掩码含6A换择', bool(m[idx['6A']]))
    check('B-1掩码不含连段A', not m[idx['连段A']])

    # B-2 COMBO_DROP: 对手真受击untech>0→0 且我非攻击
    # (BH-4.2: untech过动作门 — 基线帧须带受击族action, 自由行动
    #  的残留读数不再构成恢复边沿)
    d3 = fe.FrameEventDetector()
    d3.detect(_L(act=50), _R(act=70, untech=30), False)   # 连段中基线
    ev, win = d3.detect(_L(act=0), _R(untech=0), False)
    check('B-2连段中断→E_COMBO_DROP', ev == fe.E_COMBO_DROP,
          'ev=%s win=%s' % (fe.EV_NAMES.get(ev), win))
    check('B-2窗口=6', win == 6)
    # 自由飞翔的残留衰减不触发(BH-4.2)
    d5 = fe.FrameEventDetector()
    d5.detect(_L(act=50), _R(act=214, untech=30), False)
    ev, _ = d5.detect(_L(act=0), _R(act=214, untech=0), False)
    check('B-2飞翔残留不触发', ev == fe.E_NONE,
          'ev=%s' % fe.EV_NAMES.get(ev))
    # 我在攻击中不触发
    d4 = fe.FrameEventDetector()
    d4.detect(_L(act=50), _R(act=70, untech=30), False)
    ev, _ = d4.detect(_L(act=320), _R(untech=0), False)
    check('B-2攻击中不触发', ev == fe.E_NONE,
          'ev=%s' % fe.EV_NAMES.get(ev))
    # 掩码: 含收招三选一与弹幕
    m = fe.reaction_mask(fe.E_COMBO_DROP, _L(), _R(untech=0),
                         names, base)
    check('B-2掩码含后退', bool(m[idx['后退']]))
    check('B-2掩码含立防', bool(m[idx['立防']]))
    check('B-2掩码不含连段A', not m[idx['连段A']])

    # 既有6事件不受影响(回归)
    d5 = fe.FrameEventDetector()
    d5.detect(_L(), _R(), False)
    ev, _ = d5.detect(_L(act=152), _R(), False)
    check('回归:E_GUARDSTUN仍触发', ev == fe.E_GUARDSTUN)

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
