# -*- coding: utf-8 -*-
"""R61v(C3)行为测试: 目押门(link) — 等untech→0最速出招.
BH-4.2(2026-10-15 bug档): untech过动作门 — 等待仅在对手真受击
(action∈受击族)时成立; 自由空中行动的残留读数立即放行."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from macro_executor import (advance_queue, make_link_step,
                            just_frame_5a_2a, just_frame_2a_5a)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def st(opp_untech=0, opp_a=70):
    # BH-4.2: 默认opp_a=70(空中受击族) — untech读数有效;
    # 自由行动用opp_a=0/214验证门
    return (
        {"action": 0, "hp": 10000, "spirit": 1000,
         "position.x": 500.0, "airBorne": False, "hitStop": 0},
        {"action": opp_a, "hp": 10000,
         "position.x": 600.0, "airBorne": False,
         "untech": opp_untech},
    )


GUARD_IDS = frozenset(range(150, 167)) - {158}


def noop():
    pass


def fake_sc(left):
    return False, False, {}


def main():
    # ===== link 门行为 =====
    steps = [(("A",), 8)]
    max_wait = 20

    # 1. 对手真受击+untech>0 → 等待(不推进)
    l, r = st(opp_untech=10, opp_a=70)
    q = [make_link_step(max_wait, steps)]
    q2, gf, _, inp = advance_queue(
        q, 0, l, r, 0, 0, False, 1000, 100, "5A",
        set(), GUARD_IDS, fake_sc, noop)
    check("真受击untech>0等待", len(q2) == 1 and q2[0][0] == "link")
    check("观察窗递增", gf == 1)

    # 1b. BH-4.2: 自由行动+残留untech → 立即放行(不空等)
    for free_a in (0, 214):          # 待机/飞翔
        l, r = st(opp_untech=30, opp_a=free_a)
        q = [make_link_step(max_wait, steps)]
        q2, gf, _, _ = advance_queue(
            q, 0, l, r, 0, 0, False, 1000, 100, "5A",
            set(), GUARD_IDS, fake_sc, noop)
        check("自由行动(a=%d)立即出招" % free_a, q2 == steps and gf == 0)

    # 2. 对手untech=0 → 最速出招(link弹出+steps入队)
    # (从等待态续: 1b的循环变量已覆写q2/gf, 显式重建)
    q2, gf = [make_link_step(max_wait, steps)], 1
    l, r = st(opp_untech=0)
    q2, gf, _, _ = advance_queue(
        q2, gf, l, r, 0, 0, False, 1000, 100, "5A",
        set(), GUARD_IDS, fake_sc, noop)
    check("untech→0最速出", q2 == steps and gf == 0)

    # 3. 超时 → 截断(真受击不恢复)
    l, r = st(opp_untech=999, opp_a=70)
    q = [make_link_step(5, steps)]   # 只等5帧
    q2, _, dn, _ = advance_queue(
        q, 4, l, r, 0, 0, False, 1000, 100, "5A",
        set(), GUARD_IDS, fake_sc, noop)
    check("超时截断", len(q2) == 0 and dn is None)

    # 4. 逐步等待→恢复→最速(受击态下untech 3→2→1→0, 第4帧恢复)
    l, r = st(opp_untech=3, opp_a=70)
    q = [make_link_step(20, steps)]
    for frame in range(4):
        r["untech"] = max(0, 3 - frame)   # 3,2,1,0
        q2, gf, _, _ = advance_queue(
            q if frame == 0 else q2,
            gf, l, r, 0, 0, False, 1000, 100, "5A",
            set(), GUARD_IDS, fake_sc, noop)
        if frame < 3:
            check("帧%d仍等待(untech=%d)" % (frame, 3 - frame),
                  q2[0][0] == "link")
    check("帧3恢复→出招", q2 == steps)

    # ===== 预制目押宏 =====
    # 5. 5A→2A目押
    m = just_frame_5a_2a()
    check("目押宏名", m[0] == "目押·5A2A")
    has_confirm = any(k == "confirm" for k, _ in m[1])
    has_link = any(k == "link" for k, _ in m[1])
    check("含confirm+link", has_confirm and has_link)

    # 6. 2A→5A目押
    m2 = just_frame_2a_5a()
    check("下中目押宏名", m2[0] == "目押·2A5A")

    # 7. link在confirm之后(目押流程正确)
    confirm_idx = next(i for i, (k, _) in enumerate(m[1])
                       if k == "confirm")
    link_idx = next(i for i, (k, _) in enumerate(m[1])
                    if k == "link")
    check("link在confirm后", link_idx == confirm_idx + 1)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
