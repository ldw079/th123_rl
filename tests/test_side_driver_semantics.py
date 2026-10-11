# -*- coding: utf-8 -*-
"""R17(§3.1): 替代两条过时文本断言的行为测试。
① eval采样温度==模型_temp(原断言grep字面"temp=1.0", 行为变更后假红);
② sc:步/门步入队且frame_input能执行(原断言要求继续跳过sc步=要求旧缺陷)。
③ 决策计数递增。"""
import sys
import time

sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # 相对路径: 变异沙箱内解析到沙箱树
from side_driver import SideDriver

d = SideDriver('reimu', 'L')
d.load(r'D:\temp\th123_models\model_ppo_reimu.npz')

# ---- ① 温度跟随(间谍法: 记录sample实际收到的temp) ----
recorded = {}


def _spy_sample(feat, side, mask=None, temp=1.0, bias=None):
    recorded['temp'] = temp
    return 0


orig = d.ppo.sample
d.ppo.sample = _spy_sample
own = {"position.x": 700.0, "position.y": 100.0, "spirit": 1500,
       "hp": 9000, "airBorne": False, "direction": -1, "action": 130,
       "cardGauge": 1000, "score": 0, "hand": b'\xff' * 10,
       "comboDamage": 0, "untech": 0, "timeStop": 0, "hitStop": 0}
opp = dict(own)
opp.update({"position.x": 400.0, "direction": 1, "hp": 8000})
w = {"active": 3, "displayed": 3, "timer": 500}
objs = [(1, 500.0, 120.0, 0, 0, 0, 7)]
bul = [(1, 500.0, 120.0, -5.0, 0.0)]
# R19: 视觉栈由frame_input逐帧维护(decide不再自压帧) — 走生产路径,
# 清空队列强制每拍决策
for i in range(4):
    d.macro_queue = []
    d.frame_input(own, opp, w, objs, bul)
d.ppo.sample = orig
assert recorded.get('temp') == getattr(d.ppo, '_temp', 1.0), \
    'eval温度应==模型_temp, 实际%s' % recorded
print('✓ eval采样温度==模型_temp (%.2f)' % recorded['temp'])

# ---- ③ 决策计数 ----
assert d.decisions > 0, '决策计数未递增'
print('✓ 决策计数递增 (%d)' % d.decisions)

# ---- ② sc:步与门步能被frame_input执行 ----
d2 = SideDriver('reimu', 'L')
d2.load(r'D:\temp\th123_models\model_ppo_reimu.npz')   # abort清队后会触发decide
# sc:步: 空手牌(状态机应abort并清队) — 证明sc步真的被执行而非跳过
d2.macro_queue = [("sc:200", 0), (("A",), 3)]
inp = d2.frame_input(own, opp, w, objs, bul)
for _ in range(10):
    d2.frame_input(own, opp, w, objs, bul)   # 空手牌 → 状态机几帧内abort
assert not any(isinstance(k, str) and k.startswith("sc:")
               for k, _ in d2.macro_queue), \
    'sc步应被状态机消费, 队列仍含sc: %s' % d2.macro_queue
assert d2._sc_run is None and d2._sc_tgt is None, 'abort后状态机应复位'
print('✓ sc:步由状态机执行(空手牌→abort→复位, 队列已由新决策接管)')

# 门步: confirm观察窗 — 无伤害时4帧后裁决(证明门步在执行而非占位)
d3 = SideDriver('reimu', 'L')
d3.load(r'D:\temp\th123_models\model_ppo_reimu.npz')
d3._last_inp = {"A": True}
d3.macro_queue = [("confirm", 0), (("B",), 3)]
for _ in range(6):
    d3.frame_input(own, opp, w, objs, bul)
assert not any(isinstance(k, str) and k.startswith("confirm")
               for k, _ in d3.macro_queue), \
    '门步应在观察窗后被裁决, 队列仍含confirm: %s' % d3.macro_queue
print('✓ 门步由观察窗执行(4帧裁决)')

# sc宏掩码: 真实门控(有手牌才解锁)
assert not d2._sc_usable_mask(own).any(), '空手牌sc应全禁'
own2 = dict(own)
own2["hand"] = bytes([200, 0] * 5) if d2.char == 'suika' else \
    bytes([d2.sc_targets[list(d2.sc_targets)[0]], 0] * 5)
m = d2._sc_usable_mask(own2)
assert m.any(), '满手目标卡应解锁sc宏'
print('✓ sc掩码真实门控(解锁%d个)' % int(m.sum()))

print('\nSideDriver语义行为测试通过 ✓')
