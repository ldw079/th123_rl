# -*- coding: utf-8 -*-
"""task-58 阶段1 行为测试: 执行器命中/伤害记忆窗(TH123_EXEC_HITMEM).

背景(P1 2026-10-25): 命中帧与 hitStop 同帧 → 主循环 frozen 帧跳过
advance_queue → 该帧 d_deal 永久丢失; confirm 门 4F 窗读不到 → 首段命中
即截断(连段 200dmg/19F, 手动 A 连打可达 1510dmg). 本档用**真实帧序列**
(与隔离游戏 trace 同构: A起手 4F → 2F → 命中@f8(hitStop=9) → 冻结 9F →
解冻后 confirm 观察窗)验证:
  1) 旧行为(无 hit_mem): confirm 4F 超时截断 = 复现 bug;
  2) 记忆窗口(hit_mem=200): confirm 通过 → 宏继续走 hit 尾段;
  3) branch 门同样由记忆路由;
  4) cconfirm 语义不变;
  5) env=0/None 逐位等价;
  6) 接线锚(签名/赋值/两端env)存在.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(HERE)
sys.path.insert(0, WT)

import macro_executor as me  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def _own(action=300, hs=0, spirit=1000.0, x=500.0):
    return {"position.x": x, "position.y": 0.0, "direction": 1,
            "action": action, "spirit": spirit, "hp": 10000,
            "airBorne": False, "hitStop": hs, "timeStop": 0,
            "untech": 0, "cardGauge": 0, "score": 0,
            "comboDamage": 0, "hand": b'\xff' * 10}


def _opp(action=0, x=560.0):
    return {"position.x": x, "position.y": 0.0, "direction": -1,
            "action": action, "spirit": 1000.0, "hp": 9800,
            "airBorne": False, "untech": 0, "cardGauge": 0,
            "score": 0, "comboDamage": 0, "hand": b'\xff' * 10}


def _no_sc(own):
    return False, True, {}


def _reset():
    pass


def advance(q, gf, left, right, d, frozen=False, hit_mem=None):
    return me.advance_queue(
        q, gf, left, right, d, 0.0, frozen, 1000.0,
        float(right["position.x"]) - float(left["position.x"]),
        "连段A", set(), frozenset(range(150, 167)),
        _no_sc, _reset, hit_mem=hit_mem)


def test_confirm_old_truncates():
    """旧行为复现: 命中帧伤害丢失 → confirm 4 帧后截断."""
    q = [("confirm", 0), (("A",), 4)]
    gf = 0
    for _ in range(4):
        q, gf, _, _inp = advance(q, gf, _own(), _opp(), 0.0)
    check("confirm 旧行为4F超时截断", q == [], repr(q))


def test_confirm_memory_passes():
    """记忆窗口: 命中(200)在后 1 帧被 confirm 读到 → 通过并继续."""
    q = [("confirm", 0), (("A",), 4)]
    gf = 0
    for _ in range(3):
        q, gf, _, _ = advance(q, gf, _own(), _opp(), 0.0)
    check("记忆前仍持confirm", bool(q) and q[0][0] == "confirm", repr(q))
    q, gf, _, _ = advance(q, gf, _own(), _opp(), 0.0, hit_mem=200.0)
    check("记忆窗口confirm通过", bool(q) and q[0][0] == ("A",), repr(q))


def test_real_trace_frozen_hit():
    """真实帧序: f8命中(hitStop=9)+f9-16冻结(主循环不调执行器)+f17解冻.

    模拟调用方: frozen 帧只喂伤害历史, 不调用执行器; 解冻后 hit_mem 携带 200.
    """
    trace = [  # (frozen, d_deal, opp_action, opp_hitstop)
        (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0),
        (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0),
        (1, 200, 50, 9),  # 命中帧: 冻结+伤害
        (1, 0, 50, 8), (1, 0, 50, 7), (1, 0, 50, 6),
        (1, 0, 50, 5), (1, 0, 50, 4), (1, 0, 50, 3),
        (1, 0, 50, 2), (1, 0, 50, 1),
        (0, 0, 50, 0),  # 解冻: d_deal=0, 记忆窗=200(首确认帧→新路径通过)
        (0, 0, 50, 0), (0, 0, 50, 0), (0, 0, 50, 0),
    ]
    def _script():
        return [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4),
                (("A",), 4)]

    # 旧路径: 无记忆 → confirm 4F 超时清队(宏截断)
    q_old = _script()
    gf_old = 0
    for fz, d, oa, oh in trace:
        if fz:
            continue
        q_old, gf_old, _, _ = advance(q_old, gf_old, _own(),
                                      _opp(action=oa), d)
    check("真实帧旧路径截断(复现bug)", q_old == [], repr(q_old))
    # 新路径: hit_mem 携带冻结帧伤害 → confirm 通过, 尾段继续
    q_new = _script()
    gf_new = 0
    hm = 0.0
    for fz, d, oa, oh in trace:
        if d > 0:
            hm = float(d)
        if fz:
            continue
        q_new, gf_new, _, _ = advance(q_new, gf_new, _own(),
                                      _opp(action=oa), d,
                                      hit_mem=hm if hm > 0 else 0.0)
    check("真实帧记忆路径continue", bool(q_new) and len(q_new) >= 2,
          repr(q_new))


def test_branch_memory():
    br = {"hit": [((), 2), (("A",), 4)], "blocked": None,
          "opp_jump": None, "whiff": None}
    q = [("branch", br), (("A",), 4)]
    q2, _, _, _ = advance(q, 0, _own(), _opp(), 0.0)
    check("branch 旧行为whiff截断", q2 == [], repr(q2))
    q3 = [("branch", br), (("A",), 4)]
    q3, _, _, _ = advance(q3, 0, _own(), _opp(action=50), 0.0, hit_mem=200.0)
    check("branch 记忆窗口hit路由", bool(q3) and q3[0] == ((), 2),
          repr(q3))


def test_cconfirm_unchanged():
    q = [("cconfirm", 0), (("A",), 4)]
    gf = 0
    for _ in range(4):
        q, gf, _, _ = advance(q, gf, _own(), _opp(x=520.0), 0.0)
    check("cconfirm近距超时续段不变", bool(q) and q[0][0] == ("A",), repr(q))


def test_equivalence_env0():
    """None 与不传关键字逐位等价(旧签名兼容)."""
    for d in (0.0, 50.0, 0.0):
        qa = [("confirm", 0), (("A",), 4)]
        qb = [("confirm", 0), (("A",), 4)]
        ra = advance(qa, 0, _own(), _opp(), d)
        rb = me.advance_queue(
            qb, 0, _own(), _opp(), d, 0.0, False, 1000.0, 60.0,
            "连段A", set(), frozenset(range(150, 167)), _no_sc, _reset)
        if [x[0] for x in ra[0]] != [x[0] for x in rb[0]]:
            check("默认hit_mem=None逐位等价", False, repr((ra, rb)))
            return
    check("默认hit_mem=None逐位等价", True)


def test_wiring():
    src = open(os.path.join(WT, "macro_executor.py"),
               encoding="utf-8").read()
    tr = open(os.path.join(WT, "train_tm.py"), encoding="utf-8").read()
    sd = open(os.path.join(WT, "side_driver.py"), encoding="utf-8").read()
    check("签名含hit_mem", "hit_mem=None" in src)
    check("门评估用_dd记忆", "_dd = (float(d_deal) if hit_mem is None" in src)
    check("confirm用_dd", "if _dd > 0:" in src)
    check("train_tm env接线", "TH123_EXEC_HITMEM" in tr
          and "hit_mem=_hit_mem" in tr)
    check("side_driver env接线", "TH123_EXEC_HITMEM" in sd
          and "hit_mem=_hit_mem" in sd)


def main():
    test_confirm_old_truncates()
    test_confirm_memory_passes()
    test_real_trace_frozen_hit()
    test_branch_memory()
    test_cconfirm_unchanged()
    test_equivalence_env0()
    test_wiring()
    print("\n==== executor_hitmem: %d PASS / %d FAIL ===="
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
