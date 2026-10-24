# -*- coding: utf-8 -*-
"""分支门启用·线A(2026-10-14, plans/branch_gate_activation):

把12个confirm/cconfirm门宏升级为branch四路路由(hit/blocked/opp_jump/
whiff) — **同名同前缀**(训练面零变化: 掩码/计数/动作空间/BC前缀全兼容),
脚本内部从"二值截断"改为"多路路由"。

路由尾段纪律(R4不猜数据): 全部取自库内已实证片段 —
- hit:    原confirm门后的线性尾段(攻略hit路线原样保留)
- blocked: 磨防/磨灵变奏(压制A头与2A确认downB/版边连A的B连打片段)
- opp_jump: 对空(jA脚本: up预置+A)
- whiff:  None截断(空挥交还决策权 — 同现行为)

执行器语法: macro_executor.evaluate_branch(d_deal>0→hit;
GUARD_STUN→blocked; airBorne→opp_jump; 其余whiff)。路由步骤经
norm回调规范化(方向预置≥5帧, hitlab死招防线 — 执行器直插队列
不走macros._norm_presteps)。
"""
from __future__ import annotations

# ---- 共享路由片段(库内已实证) ----
_AA = [(("up",), 6), (("A",), 10)]                     # jA对空
_2B_PRESSURE = [((), 3), (("down",), 6), (("down", "B"), 10),
                ((), 3), (("down",), 6), (("down", "A"), 8)]   # 2B→2A磨防
_B_GRIND = [((), 3), (("B",), 10), ((), 2), (("B",), 10)]      # B磨灵
_5A_CHASE = [((), 2), (("A",), 8)]                      # 5A追击(压起身·即片段)

# 各宏blocked/opp_jump定制(hit=原尾段自动继承; None=该路截断)
# 压制系cconfirm宏: blocked给**不同于hit尾段**的变奏(原语义命中/被防
# 都走同尾段 — branch化后被防改走磨防变奏, 命中仍走连段)
BLOCKED_ROUTES = {
    "5A确认": _2B_PRESSURE,
    "2A确认": _2B_PRESSURE,
    "原子·确认5A": _2B_PRESSURE,
    # task-33(2026-10-24 数据修复): 连段A/B/C/版边连A 退出 branch 升级 ——
    # 根因: branch 只在门那一帧读 d_deal, 而 A 起手命中发生在门前 1-3 帧
    # (2 中性帧后) → 命中被误判 whiff → 连段截断(replay 0% 命中
    # dmg≥300). 原 confirm 门有 4 帧伤害窗口 → 保留确认语义更可靠.
    # 版边连A 已被 BLOCKED_ROUTES 覆盖(见下) — 同步退出.
    "压制A": _2B_PRESSURE,          # 被防: 2A头换2B磨防(原走6A连段)
    "压制B": _B_GRIND,             # 被防: C压制换B磨灵
    "空连A": [(("left",), 8)],      # 被防: 空防保持(空防left段片段)
    "TM·2a连": None,               # 被防: 截断(计划A-2表)
    "TM·4a连": None,
}
OPP_JUMP_ROUTES = {                 # 缺省jA对空
    "空连A": [(("up",), 6), (("A",), 10)],   # 空对空
}
# 原子·确认5A无原尾段(纯探针宏) — hit给5A追击
HIT_OVERRIDE = {
    "原子·确认5A": _5A_CHASE,
}

GATE_STEPS = ("confirm", "cconfirm")


def _mk_branch(hit, blocked, opp_jump):
    return ("branch", {"hit": hit, "blocked": blocked,
                       "opp_jump": opp_jump, "whiff": None})


def upgrade_branches(macros, norm=None):
    """把GATED宏的(confirm,0)+线性尾段升级为branch四路。

    macros: [(名, 脚本)] — 已规范化的MACROS; 前缀(门前步)原样保留。
    norm: 路由步骤规范化回调(macros._norm_presteps — 防执行器直插
    队列绕过hitlab方向预置)。返回新列表(不改输入)。
    """
    out = []
    n_up = 0
    for name, script in macros:
        gate_i = None
        for i, (ks, fr) in enumerate(script):
            if isinstance(ks, str) and ks in GATE_STEPS:
                gate_i = i
                break
        if gate_i is None or name not in BLOCKED_ROUTES:
            out.append((name, script))
            continue
        prefix = list(script[:gate_i])
        hit = HIT_OVERRIDE.get(name) or list(script[gate_i + 1:])
        blocked = BLOCKED_ROUTES[name]
        opp_jump = OPP_JUMP_ROUTES.get(name, _AA)
        if norm is not None:
            hit = norm(hit)
            blocked = norm(blocked) if blocked else None
            opp_jump = norm(opp_jump)
        out.append((name, prefix + [_mk_branch(hit, blocked, opp_jump)]))
        n_up += 1
    print('[macros_branch] %d宏升级为branch四路(名/前缀不变)' % n_up)
    return out
