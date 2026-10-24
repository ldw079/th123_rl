# -*- coding: utf-8 -*-
"""分支门启用·线A行为测试(A-3.3, 2026-10-14): 12宏×4路路由。

宏库→入队→执行器→分支→路由步骤: 用真实升级后宏驱动 advance_queue,
hit(d_deal>0)/blocked(对手GUARD_STUN)/opp_jump(对手airBorne)/
whiff(其余) 四路各验一条 — 与test_executor_integration互补
(彼测脚本语义, 此测真实宏库路由)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

import macro_executor as me                    # noqa: E402
from macros import MACROS                      # noqa: E402

PASS, FAIL = [], []
UPGRADED = ['5A确认', '2A确认',
            '压制A', '压制B', '空连A',
            'TM·2a连', 'TM·4a连', '原子·确认5A']
# task-33: 连段A/B/C/版边连A 退出 branch(confirm 4F 伤害窗修复取消步时序)


def _no_sc(left):
    return False, True, {}


def _sc_reset():
    pass


def _own(x=500.0, act=0):
    return {"position.x": x, "position.y": 0.0, "direction": 1,
            "action": act, "spirit": 1000.0, "hp": 10000,
            "airBorne": False, "hitStop": 0, "timeStop": 0,
            "untech": 0, "cardGauge": 0, "score": 0,
            "comboDamage": 0, "hand": b'\xff' * 10}


def _opp(x=700.0, act=0, air=False):
    return {"position.x": x, "position.y": 0.0, "direction": -1,
            "action": act, "spirit": 1000.0, "hp": 10000,
            "airBorne": air, "untech": 0, "cardGauge": 0,
            "score": 0, "comboDamage": 0, "hand": b'\xff' * 10}


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def drive_to_gate(script):
    """入队并推进到branch门位于队首(消耗门前缀步)。"""
    q = me.enqueue_script([], list(script))
    for _ in range(400):
        if q and isinstance(q[0][0], str) and q[0][0] == 'branch':
            return q
        q, _, _, _ = me.advance_queue(
            q, 0, _own(), _opp(), 0, 0, False, 1000.0, 200.0,
            "测试", set(), frozenset(), _no_sc, _sc_reset)
        if not q:
            return q
    return q


def first_route_step(branch_dict, route):
    """路由首键步(规范: 路由步已预置方向, 首步可能是方向保持步)."""
    steps = branch_dict.get(route)
    if not steps:
        return None
    for ks, fr in steps:
        if not isinstance(ks, str):
            return ks
    return None


def main():
    libd = dict(MACROS)
    for name in UPGRADED:
        script = libd[name]
        br = [fr for ks, fr in script
              if isinstance(ks, str) and ks == 'branch']
        check("%s含branch门" % name, len(br) == 1)
        if not br:
            continue
        bd = br[0]
        q = drive_to_gate(script)
        check("%s前缀可推进到门" % name,
              bool(q) and isinstance(q[0][0], str)
              and q[0][0] == 'branch', str(q[:1]))
        if not q or q[0][0] != 'branch':
            continue
        # hit: d_deal>0
        qh, _, _, _ = me.advance_queue(
            list(q), 0, _own(), _opp(), 60, 0, False, 1000.0,
            200.0, name, set(), frozenset(), _no_sc, _sc_reset)
        exp_h = first_route_step(bd, 'hit')
        got_h = next((s[0] for s in qh if not isinstance(s[0], str)),
                     None)
        check("%s hit路路由" % name,
              got_h is not None and exp_h is not None
              and tuple(got_h) == tuple(exp_h),
              'exp=%s got=%s' % (exp_h, got_h))
        # blocked: 对手GUARD_STUN(152)
        qb, _, _, _ = me.advance_queue(
            list(q), 0, _own(), _opp(act=152), 0, 0, False, 1000.0,
            200.0, name, set(), frozenset(), _no_sc, _sc_reset)
        if bd.get('blocked') is None:
            check("%s blocked=截断" % name, qb == [])
        else:
            exp_b = first_route_step(bd, 'blocked')
            got_b = next((s[0] for s in qb if not isinstance(s[0], str)),
                         None)
            check("%s blocked路路由" % name,
                  got_b is not None and tuple(got_b) == tuple(exp_b),
                  'exp=%s got=%s' % (exp_b, got_b))
        # opp_jump: 对手airBorne
        qj, _, _, _ = me.advance_queue(
            list(q), 0, _own(), _opp(air=True), 0, 0, False, 1000.0,
            200.0, name, set(), frozenset(), _no_sc, _sc_reset)
        exp_j = first_route_step(bd, 'opp_jump')
        got_j = next((s[0] for s in qj if not isinstance(s[0], str)),
                     None)
        check("%s opp_jump路路由" % name,
              got_j is not None and tuple(got_j) == tuple(exp_j),
              'exp=%s got=%s' % (exp_j, got_j))
        # whiff: 无证据 → 截断
        qw, _, _, _ = me.advance_queue(
            list(q), 0, _own(), _opp(), 0, 0, False, 1000.0,
            200.0, name, set(), frozenset(), _no_sc, _sc_reset)
        check("%s whiff截断" % name, qw == [])

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
