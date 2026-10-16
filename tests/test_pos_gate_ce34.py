# -*- coding: utf-8 -*-
"""CE-3.4行为测试: 位置路由门(pos_gate) — 贴角/版中两态注入→同宏
走出不同续段(方案验收判据) + 外推路由 + 回落语义 + P1-4保留名."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from macro_executor import (advance_queue, enqueue_script,
                            evaluate_position_gate, adaptive_combo,
                            make_pos_gate_step, POS_GATE_THRESHOLD)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def st(opp_x=600.0, my_x=500.0, opp_a=0, my_a=0, untech=0):
    return (
        {"action": my_a, "hp": 10000, "spirit": 1000,
         "position.x": my_x, "airBorne": False, "hitStop": 0},
        {"action": opp_a, "hp": 10000, "position.x": opp_x,
         "airBorne": False, "untech": untech},
    )


GUARD_IDS = frozenset(range(150, 167)) - {158}
GUARD_PREP = set()


def noop():
    pass


def fake_sc(left):
    return False, False, {}


CORNER = [(("B",), 10)]
MID = [(("C",), 10)]


def main():
    # ===== 单元: evaluate_position_gate =====
    # 1. 对手贴左角 → corner
    l, r = st(opp_x=100.0)
    res = evaluate_position_gate(
        make_pos_gate_step(CORNER, MID)[1], l, r)
    check("贴左角→corner", res == CORNER)

    # 2. 版中 → mid
    l, r = st(opp_x=640.0)
    res = evaluate_position_gate(
        make_pos_gate_step(CORNER, MID)[1], l, r)
    check("版中→mid", res == MID)

    # 3. 右角对称
    l, r = st(opp_x=1180.0)
    res = evaluate_position_gate(
        make_pos_gate_step(CORNER, MID)[1], l, r)
    check("贴右角→corner(对称)", res == CORNER)

    # 4. 外推: 版中250px+推板150 → 预测100<120 → corner
    l, r = st(opp_x=250.0)
    res = evaluate_position_gate(
        make_pos_gate_step(CORNER, MID, dx_opp_hint=150.0)[1], l, r)
    check("外推入角→corner", res == CORNER)
    # 同位置无外推 → mid(外推真实生效的负对照)
    res = evaluate_position_gate(
        make_pos_gate_step(CORNER, MID)[1], l, r)
    check("同位置无外推→mid(负对照)", res == MID)

    # 5. corner键缺省 → 回落mid(已确认连段不截断)
    payload = {"mid": MID}
    l, r = st(opp_x=100.0)
    res = evaluate_position_gate(payload, l, r)
    check("corner缺省→回落mid", res == MID)

    # 6. corner显式None+mid None → 截断
    payload = {"corner": None, "mid": None}
    l, r = st(opp_x=100.0)
    res = evaluate_position_gate(payload, l, r)
    check("双None→截断", res is None)

    # 7. 阈值默认=R23口径120
    check("默认阈值120(R23口径)", POS_GATE_THRESHOLD == 120.0)
    # 边界: 121px>120 → mid; 119px → corner
    l, r = st(opp_x=119.0)
    check("119px→corner(界内)",
          evaluate_position_gate(
              make_pos_gate_step(CORNER, MID)[1], l, r) == CORNER)
    l, r = st(opp_x=121.0)
    check("121px→mid(界外)",
          evaluate_position_gate(
              make_pos_gate_step(CORNER, MID)[1], l, r) == MID)

    # ===== 贯通: 同宏贴角/版中两态 → 不同续段(方案验收判据) =====
    def _run_macro(opp_x):
        """跑 起手→confirm(命中)→pos_gate 到续段首键发出."""
        script = [(("A",), 1), ("confirm", 0),
                  make_pos_gate_step(CORNER, MID)]
        q = enqueue_script([], script)
        l, r = st(opp_x=opp_x)
        dx = r["position.x"] - l["position.x"]
        # 帧1: 起手按键步耗尽弹出
        q, _, _, _ = advance_queue(
            q, 0, l, r, 0, 0, False, 1000, dx, "连段A·自适应",
            GUARD_PREP, GUARD_IDS, fake_sc, noop)
        # 帧2: confirm命中通过(d_deal>0)
        q, _, _, _ = advance_queue(
            q, 0, l, r, 500, 0, False, 1000, dx, "连段A·自适应",
            GUARD_PREP, GUARD_IDS, fake_sc, noop)
        # 帧3: pos_gate路由(不发键)
        q, _, _, _ = advance_queue(
            q, 0, l, r, 0, 0, False, 1000, dx, "连段A·自适应",
            GUARD_PREP, GUARD_IDS, fake_sc, noop)
        # 帧4: 续段首键发出
        q, _, _, inp = advance_queue(
            q, 0, l, r, 0, 0, False, 1000, dx, "连段A·自适应",
            GUARD_PREP, GUARD_IDS, fake_sc, noop)
        return inp

    inp_corner = _run_macro(100.0)
    inp_mid = _run_macro(640.0)
    check("贴角态→续段B键", inp_corner is not None
          and inp_corner.get("B") is True
          and inp_corner.get("C") is None)
    check("版中态→续段C键", inp_mid is not None
          and inp_mid.get("C") is True
          and inp_mid.get("B") is None)
    check("同宏两态续段不同(验收判据)",
          inp_corner.get("B") != inp_mid.get("B"))

    # ===== P1-4: pos_gate截断保留dec_name(正常截断结算空挥口径) =====
    q = enqueue_script([], [(("A",), 1),
                            make_pos_gate_step(None, None)])
    l, r = st(opp_x=100.0)
    q, _, dn, _ = advance_queue(
        q, 0, l, r, 0, 0, False, 1000, 100.0, "宏名",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    q, _, dn, _ = advance_queue(
        q, 0, l, r, 0, 0, False, 1000, 100.0, dn,
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("pos_gate截断保留dec_name", len(q) == 0 and dn == "宏名")

    # ===== 模板: adaptive_combo结构 =====
    tpl = adaptive_combo([(("A",), 8)], CORNER, MID, dx_opp_hint=80.0)
    check("模板含confirm+pos_gate",
          any(s[0] == "confirm" for s in tpl)
          and any(s[0] == "pos_gate" for s in tpl))
    pg = [s for s in tpl if s[0] == "pos_gate"][0][1]
    check("模板载荷齐全",
          pg["corner"] == CORNER and pg["mid"] == MID
          and pg["dx_opp_hint"] == 80.0
          and pg["threshold"] == 120.0)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
