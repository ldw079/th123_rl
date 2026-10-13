# -*- coding: utf-8 -*-
"""R61u(C1)行为测试: 统一宏执行器+分支门系统."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from macro_executor import (advance_queue, evaluate_branch,
                            make_branch_step, oki_branch,
                            mixup_branch_variants)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def st(my_a=0, opp_a=0, my_hp=10000, opp_hp=10000, spirit=1000):
    return (
        {"action": my_a, "hp": my_hp, "spirit": spirit,
         "position.x": 500.0, "airBorne": False,
         "hitStop": 0},
        {"action": opp_a, "hp": opp_hp,
         "position.x": 600.0, "airBorne": False},
    )


GUARD_IDS = frozenset(range(150, 167)) - {158}
GUARD_PREP = {"立防", "蹲防"}


def noop():
    pass


def fake_sc(left):
    return False, False, {}


def main():
    # ===== 分支门评估 =====
    br = {"hit": [("A", 6)], "blocked": [("B", 6)],
          "opp_jump": [("C", 6)], "whiff": None}

    # 1. 命中→hit分支
    l, r = st()
    result = evaluate_branch(br, l, r, d_deal=100, d_take=0)
    check("命中→hit", result == [("A", 6)])

    # 2. 被防→blocked分支
    l, r = st(opp_a=155)
    result = evaluate_branch(br, l, r, d_deal=0, d_take=0)
    check("被防→blocked", result == [("B", 6)])

    # 3. 对手空中→opp_jump分支(注意: 需非防御态, 防御优先于空中)
    l2, r2 = st()
    r2["airBorne"] = True
    result = evaluate_branch(br, l2, r2, d_deal=0, d_take=0)
    check("空中→opp_jump", result == [("C", 6)])

    # 4. 空挥→whiff(None=截断)
    l, r = st()
    result = evaluate_branch(br, l, r, d_deal=0, d_take=0)
    check("空挥→None(截断)", result is None)

    # 5. 无对应分支→None
    br2 = {"hit": [("A", 6)]}   # 只有hit分支
    l, r = st()
    result = evaluate_branch(br2, l, r, d_deal=0, d_take=0)
    check("无whiff分支→None", result is None)

    # ===== 队列推进(基础) =====
    # 6. 按键步推进
    q = [(("A",), 3)]
    l, r = st()
    q2, gf, dn, inp = advance_queue(
        q, 0, l, r, 0, 0, False, 1000, 100, None,
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("按键步减帧", len(q2) == 1 and q2[0][1] == 2)
    check("按键步产生输入", inp is not None and inp.get("A") is True)

    # 7. 帧耗尽→弹出(fl=1时减到0弹出)
    q_single = [(("A",), 1)]
    q3, _, _, _ = advance_queue(
        q_single, 0, l, r, 0, 0, False, 1000, 100, None,
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("帧尽弹出", len(q3) == 0)

    # 8. 受击中止
    q = [(("A",), 10)]
    q2, _, dn2, _ = advance_queue(
        q, 0, l, r, 0, 100, False, 1000, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("受击中止", len(q2) == 0 and dn2 is None)

    # 8b. R34中断(从零#2迁移变异#74的承接断言): 对手攻击+我方硬直
    # +近距+非防御预备 → 清队交还控制
    l34, r34 = st(my_a=50, opp_a=400)
    q = [(("A",), 10)]
    q2, _, dn2, _ = advance_queue(
        q, 0, l34, r34, 0, 0, False, 1000, 100, "连段A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("R34中断(硬直遇攻)", len(q2) == 0 and dn2 is None)
    # R34豁免: 防御预备宏不清队(立防启动窗口)
    q = [(("A",), 10)]
    q2, _, _, _ = advance_queue(
        q, 0, l34, r34, 0, 0, False, 1000, 100, "立防",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("R34豁免(防御预备)", len(q2) == 1)
    # 审计#3 P1-2: None形态 — 旧side_driver恒传None → 同条件下被清
    # (对手侧守备窗从不豁免的训练信号偏斜根源), 两侧对称性承接断言
    q = [(("A",), 10)]
    q2, _, _, _ = advance_queue(
        q, 0, l34, r34, 0, 0, False, 1000, 100, None,
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("R34对None不豁免(对称性基准)", len(q2) == 0)
    _sd = open(os.path.join(os.path.dirname(__file__), '..',
                            'side_driver.py'), encoding='utf8').read()
    # ===== 审计#3 P2: delay_then活体断言(执行器支持, 生产者=分支字典
    # 元组值; 原无任何测试="文档有代码无测试"第三态) =====
    q = [("branch", {"hit": (6, [(("A",), 3)])}), (("B",), 5)]
    l, r = st(my_a=0, opp_a=0)
    q2, gf, dn, inp = advance_queue(
        q, 0, l, r, 100, 0, False, 1000, 800, None,
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    # hit条件: d_deal=100>0 → 命中分支 → 变(6帧空步 + A步 + B步)
    check("delay_then分支命中展开为6空帧+后续步",
          len(q2) == 3 and q2[0] == ((), 6) and q2[1] == (("A",), 3)
          and q2[2] == (("B",), 5), str(q2))

    check("side_driver传self._dec_name(接线不回退)",
          'self._dec_name,' in _sd and 'self._dec_name = None' in _sd)

    # 8c. 灵力门(迁移变异#75承接): 空灵力+下一含攻击键 → 清队
    l35, r35 = st(my_a=0, opp_a=0, spirit=50)
    q = [(("A",), 10)]
    q2, _, _, _ = advance_queue(
        q, 0, l35, r35, 0, 0, False, 50, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("灵力门(空灵力清队)", len(q2) == 0)

    # 8d. 空队安全(迁移变异#76语义承继): 清队路径全部立即return,
    # 空队列推进不得异常且不发输入
    q4, _, _, inp4 = advance_queue(
        [], 0, l, r, 0, 0, False, 1000, 100, None,
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("空队安全", q4 == [] and inp4 is None)

    # 9. confirm门: 命中通过
    q = [("confirm", 0), (("A",), 5)]
    q2, gf, _, _ = advance_queue(
        q, 0, l, r, 100, 0, False, 1000, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("confirm命中通过", q2 == [(("A",), 5)] and gf == 0)

    # 10. confirm门: 超时截断
    q = [("confirm", 0), (("A",), 5)]
    q2, _, dn3, _ = advance_queue(
        q, 3, l, r, 0, 0, False, 1000, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("confirm超时截断", len(q2) == 0)

    # ===== 分支门在队列中 =====
    # 11. 分支步: hit路由
    q = [make_branch_step(br)]
    q2, _, _, _ = advance_queue(
        q, 0, l, r, 100, 0, False, 1000, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("分支hit路由", q2 == [("A", 6)])

    # 12. 分支步: whiff截断
    q = [make_branch_step(br)]
    q2, _, _, _ = advance_queue(
        q, 0, l, r, 0, 0, False, 1000, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("分支whiff截断", len(q2) == 0)

    # 13. delay_then: 放帧
    br_delay = {"hit": (3, [("A", 6)])}  # 延迟3帧
    q = [make_branch_step(br_delay)]
    q2, _, _, _ = advance_queue(
        q, 0, l, r, 100, 0, False, 1000, 100, "5A",
        GUARD_PREP, GUARD_IDS, fake_sc, noop)
    check("delay_then放帧", len(q2) == 2 and q2[0] == ((), 3))

    # ===== 预制宏模板 =====
    # 14. 拍子宏
    tempos = mixup_branch_variants('reimu', [])
    check("拍子三变体", len(tempos) == 3
          and all(n.startswith('拍子·') for n, _ in tempos))

    # 15. 压起身分支宏
    oki = oki_branch('reimu')
    check("压起身分支宏", oki[0] == "压起身·分支")
    has_branch = any(isinstance(k, str) and k == "branch"
                     for k, _ in oki[1])
    check("含分支步", has_branch)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
