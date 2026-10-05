# -*- coding: utf-8 -*-
"""R61d(A3裁决)帧级事件边沿行为测试:
F-13: 正防硬直(150-157)必须触发GUARDSTUN(R51版不可见); 158空防状态
      不触发; 错防(159-166)触发; 退出硬直触发GUARDSTUN_END。
F-12: 站立受击恢复(50→0)不触发WAKEUP(hitlab H1实证旧沿误判); 真倒地
      (97/98/88/89/100/143/145→0)触发。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from frame_events import (FrameEventDetector, E_NONE, E_GUARDSTUN,  # noqa
                          E_GUARDSTUN_END, E_WAKEUP, _GUARD_STUN_IDS,
                          _TRUE_DOWN_ACTS)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def st(my_a, opp_a=0):
    return ({"action": my_a, "untech": 0, "airBorne": False,
             "position.x": 500.0, "position.y": 0.0},
            {"action": opp_a, "position.x": 600.0, "position.y": 0.0})


def events(seq):
    """跑帧序列(元素=int或(my,opp)元组), 返回触发的事件列表。"""
    det = FrameEventDetector()
    out = []
    for item in seq:
        if isinstance(item, tuple):
            my_a, opp_a = item
        else:
            my_a, opp_a = item, 0
        l, r = st(my_a, opp_a)
        ev, _ = det.detect(l, r, False)
        if ev != E_NONE:
            out.append(ev)
    return out


def main():
    check("集合语义: 150-157正防入族", 150 in _GUARD_STUN_IDS
          and 157 in _GUARD_STUN_IDS and 159 in _GUARD_STUN_IDS
          and 166 in _GUARD_STUN_IDS)
    check("集合语义: 158/167/149不入族", 158 not in _GUARD_STUN_IDS
          and 167 not in _GUARD_STUN_IDS and 149 not in _GUARD_STUN_IDS)
    check("集合语义: 真倒地集=7枚", _TRUE_DOWN_ACTS ==
          frozenset({88, 89, 97, 98, 100, 143, 145}))

    # F-13: 正防触发(旧沿159-167不可见 — 本测试即A3裁决的行为钉)
    ev = events([0, 151, 151, 0])
    check("正防151→GUARDSTUN", ev and ev[0] == E_GUARDSTUN, str(ev))
    check("退出→GUARDSTUN_END", ev[-1] == E_GUARDSTUN_END, str(ev))
    ev = events([0, 154, 0])   # 正防下段
    check("正防154(下段)→触发", ev and ev[0] == E_GUARDSTUN)
    ev = events([0, 159, 0])   # 错防
    check("错防159→触发", ev and ev[0] == E_GUARDSTUN)
    ev = events([0, 158, 0])   # 空防状态(非硬直边沿)
    check("空防158不触发GUARDSTUN", E_GUARDSTUN not in ev, str(ev))

    # F-12: 站立受击恢复≠起身
    ev = events([0] + [50] * 20 + [0])
    check("站立受击50→0不触发WAKEUP", E_WAKEUP not in ev, str(ev))
    ev = events([0] + [71] * 15 + [0])   # 蹲姿受击
    check("蹲姿受击71→0不触发WAKEUP", E_WAKEUP not in ev, str(ev))
    ev = events([0] + [97] * 10 + [0])
    check("倒地97→0触发WAKEUP", E_WAKEUP in ev, str(ev))
    ev = events([0] + [98] * 10 + [0])
    check("倒地98→0触发WAKEUP", E_WAKEUP in ev, str(ev))
    ev = events([0] + [88] * 8 + [0])
    check("砸地88→0触发WAKEUP", E_WAKEUP in ev, str(ev))
    ev = events([0] + [100] * 12 + [0])
    check("被投100→0触发WAKEUP", E_WAKEUP in ev, str(ev))
    ev = events([0] + [143] * 10 + [0])
    check("压溃143→0触发WAKEUP", E_WAKEUP in ev, str(ev))
    ev = events([0] + [70] * 10 + [0])   # 普通空中受击(非砸地)
    check("普通空受70→0不触发WAKEUP", E_WAKEUP not in ev, str(ev))

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
