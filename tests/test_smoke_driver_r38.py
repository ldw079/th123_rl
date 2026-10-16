# -*- coding: utf-8 -*-
"""R38冒烟测试(第九轮审计P0行动项3): 合成帧驱动SideDriver.frame_input,
覆盖R34中断各分支/受击中止/灵力门控/门步/sc步 — 断言无异常且行为正确。

背景: P0-1(IndexError)与P0-2(NameError)均为"新路径无可达性测试"的产物。
本测试不加载真实模型(decide打桩), 纯驱动队列推进逻辑。
"""
import sys

sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # 沙箱内相对解析
from side_driver import SideDriver

BASE = {"position.x": 700.0, "position.y": 100.0, "spirit": 1500,
        "hp": 10000, "airBorne": False, "direction": -1, "action": 130,
        "cardGauge": 1000, "score": 0, "hand": b'\xff' * 10,
        "comboDamage": 0, "untech": 0, "timeStop": 0, "hitStop": 0}
W = {"active": 3, "displayed": 3, "timer": 500}
OBJS = [(1, 500.0, 120.0, 0, 0, 0, 7)]
BUL = [(1, 500.0, 120.0, -5.0, 0.0)]


def mk_driver():
    d = SideDriver('reimu', 'L')
    d.decide = lambda *a, **k: None    # 不加载模型 — 只测队列推进/中断
    return d


def frame(d, own, opp):
    d.frame_input(own, opp, W, OBJS, BUL)


# ---- 1) 受击中止 + R34不成立(对手非攻击态) → 清队不炸(P0-1同类路径) ----
d = mk_driver()
d.macro_queue = [(("A",), 3)]
own = dict(BASE)
own["hp"] = 9800                  # d_take=200>80 触发受击中止
opp = dict(BASE)
opp.update({"position.x": 600.0, "action": 130})   # 非攻击态 → R34短路
frame(d, own, opp)
assert d.macro_queue == [], '受击中止应清队: %s' % d.macro_queue
print('✓ 受击中止清队无异常(远距被弹幕命中场景)')

# ---- 2) R34中断: 对手攻击+我方硬直+近距 → 清队(P0-2: GUARD_ALL_IDS求值) ----
d = mk_driver()
d.macro_queue = [(("A",), 3)]
own = dict(BASE)
own["action"] = 50                # <100 硬直/移动
opp = dict(BASE)
opp.update({"position.x": 600.0, "action": 400})   # 攻击态300-598
frame(d, own, opp)
assert d.macro_queue == [], 'R34中断应清队: %s' % d.macro_queue
print('✓ R34中断清队(GUARD_ALL_IDS可解析 — 导入缺失会在此NameError)')

# ---- 2b) 我方在防御态 → R34不误触 ----
d = mk_driver()
d.macro_queue = [(("2",), 3)]
own = dict(BASE)
own["action"] = 150               # GUARD_STANCE_IDS ⊂ GUARD_ALL_IDS
opp = dict(BASE)
opp.update({"position.x": 600.0, "action": 400})
frame(d, own, opp)
assert len(d.macro_queue) == 1, '防御态不应被R34中断: %s' % d.macro_queue
print('✓ R34不误触防御态')

# ---- 3) 灵力门控(裁定四A, 2026-10-14): B/C真耗灵键+灵力不足→清队;
# 近战A零灵耗放行(原连带清空=残血没收近战手段) ----
d = mk_driver()
d.macro_queue = [(("B",), 3)]
own = dict(BASE)
own["spirit"] = 50
opp = dict(BASE)
opp.update({"position.x": 1000.0, "action": 130})   # 远距 → R34不触发
frame(d, own, opp)
assert d.macro_queue == [], '灵力门控应清队(B): %s' % d.macro_queue
d = mk_driver()
d.macro_queue = [(("A",), 3)]
frame(d, dict(own), dict(opp))
assert d.macro_queue, '灵力门放行近战A(裁定四A): %s' % d.macro_queue
print('✓ 灵力门控清队(攻击步+灵力<100)')

# ---- 3b) 移动键+灵力不足 → 保留 ----
d = mk_driver()
d.macro_queue = [(("2",), 3)]
own = dict(BASE)
own["spirit"] = 50
opp = dict(BASE)
opp.update({"position.x": 1000.0, "action": 130})
frame(d, own, opp)
assert len(d.macro_queue) == 1, '移动键不应被灵力门控清队: %s' % d.macro_queue
print('✓ 灵力门控不误触移动键')

# ---- 4) 普通键推进: fl递减到0弹出 ----
d = mk_driver()
d.macro_queue = [(("2",), 2)]
own = dict(BASE)
opp = dict(BASE)
opp.update({"position.x": 600.0, "action": 130})
frame(d, own, opp)
assert d.macro_queue == [(("2",), 1)], 'fl应递减: %s' % d.macro_queue
frame(d, own, opp)
assert d.macro_queue == [], 'fl到0应弹出: %s' % d.macro_queue
print('✓ 普通键按帧推进')

# ---- 5) cconfirm门步: 贴身无伤4帧后放行 ----
d = mk_driver()
d._last_inp = {"A": True}
d.macro_queue = [("cconfirm", 0), (("A",), 3)]
for _ in range(5):
    frame(d, own, opp)
assert not any(isinstance(k, str) for k, _ in d.macro_queue), \
    'cconfirm贴身应放行: %s' % d.macro_queue
print('✓ cconfirm门步贴身放行')

# ---- 6) sc步: 空手牌 → abort清队复位 ----
d = mk_driver()
d.macro_queue = [("sc:200", 0), (("A",), 3)]
for _ in range(12):
    frame(d, own, opp)
assert not any(isinstance(k, str) and k.startswith("sc:")
               for k, _ in d.macro_queue), 'sc步应被状态机消费: %s' % d.macro_queue
assert d._sc_run is None and d._sc_tgt is None, 'abort后状态机应复位'
print('✓ sc步状态机执行(空手牌abort)')

print('\nR38冒烟测试通过 ✓')
