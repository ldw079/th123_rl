# -*- coding: utf-8 -*-
"""裁定一1e行为测试: 后退/立防按对手攻击态重归属(refine_guard_labels).

输入全同(按住后)仅对手攻击态可分: 对手攻击/射击窗口内=立防, 否则=后退。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from bc_build import refine_guard_labels          # noqa: E402
from action_tables import reimu_ATTACK_IDS       # noqa: E402
from train_tm import CHAR_LIBS                   # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def mk_frames(opp_actions, n=80):
    """合成帧列表: 对手action按帧指定, 其余字段最小化."""
    fr = []
    for i in range(n):
        fr.append(({'action': 0}, {'action': opp_actions.get(i, 0)}, {}, ()))
    return fr


def main():
    lib = CHAR_LIBS['reimu']['macros']
    idx_back = [i for i, m in enumerate(lib) if m[0] == '后退'][0]
    idx_guard = [i for i, m in enumerate(lib) if m[0] == '立防'][0]
    atk = sorted(reimu_ATTACK_IDS)[0]

    hits = [(50, idx_back, 1.0), (65, idx_guard, 1.0)]
    # 对手在50+3帧进入攻击 → 帧50的后退应重归立防; 帧65无攻击 → 立防改后退
    fr = mk_frames({53: atk})
    out = refine_guard_labels(hits, fr, 0, lib)
    got = {h[0]: h[1] for h in out}
    check("攻击窗口内后退→立防", got[50] == idx_guard)
    check("无攻击窗口立防→后退", got[65] == idx_back)

    # 非防御宏透传不变
    idx_5b = [i for i, m in enumerate(lib) if m[0] == '5B'][0]
    out = refine_guard_labels([(40, idx_5b, 0.99)], mk_frames({41: atk}), 0, lib)
    check("非防御宏透传", out == [(40, idx_5b, 0.99)])

    # 未知对手角色(池外) → 用全集, 攻击态仍可判
    out = refine_guard_labels([(50, idx_back, 1.0)], mk_frames({55: atk}),
                              99, lib)
    check("池外对手用全集", out[0][1] == idx_guard)

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
