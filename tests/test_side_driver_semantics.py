# -*- coding: utf-8 -*-
"""R17(§3.1): 替代两条过时文本断言的行为测试。
① eval采样温度==模型_temp(原断言grep字面"temp=1.0", 行为变更后假红);
② sc:步/门步入队且frame_input能执行(原断言要求继续跳过sc步=要求旧缺陷)。
③ 决策计数递增。"""
import sys
import time

sys.stdout.reconfigure(encoding='utf8')
import os as _os

import numpy as np
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # 相对路径: 变异沙箱内解析到沙箱树
from side_driver import SideDriver

d = SideDriver('reimu', 'L')
d.load(r'D:\temp\th123_models\model_ppo_reimu.npz')

# ---- ① 温度跟随(间谍法: 记录sample实际收到的temp) ----
recorded = {}


def _spy_sample(feat, side, mask=None, temp=1.0, bias=None,
                return_pred=False):
    recorded['temp'] = temp
    return (0, (0, 0.5)) if return_pred else 0


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

# ---- P1-6(从零#5): 评估侧对手角色注入 ----
# 训练侧由 train_tm 给 P2 驱动注入 opp_char_id; 评估工具此前从不设置 →
# 对手 one-hot 段全零, 与训练分布不符。本测试直接**行为验证**注入生效。
d4 = SideDriver('reimu', 'L')
d4.load(r'D:\temp\th123_models\model_ppo_reimu.npz'
        if __import__('os').path.exists(
            r'D:\temp\th123_models\model_ppo_reimu.npz') else None)
_seq = []
_orig4 = d4.ppo.sample


def _spy4(feat, side, mask=None, temp=1.0, bias=None, return_pred=False):
    _seq.append(np.array(side, copy=True))
    return (0, (0, 0.5)) if return_pred else 0


assert d4.set_opponent('sakuya') == 11, 'sakuya应解析为池序11'
d4.ppo.sample = _spy4
d4.macro_queue = []
for _ in range(4):
    d4.macro_queue = []
    d4.frame_input(own, opp, w, objs, bul)
d4.ppo.sample = _orig4
_s = _seq[-1] if _seq else None
_core_off = 2 * d4.n_macros
assert _s is not None and _s[_core_off + 227 + 11] > 0.5, \
    '对手角色槽 core[227+11] 应为1(实际%.1f)' % (
        _s[_core_off + 227 + 11] if _s is not None else -1)
assert _s[_core_off + 227 + 0] < 0.5, '非对手槽不得误置'
assert d4.feat_builder.opp_outside_pool == 1.0, '池外位应随id派生=1'
print('✓ 对手角色注入生效(core[227+11]=1, 池外位=1)')

# 未知角色: 不猜(保持None, 槽位全零)
d5 = SideDriver('reimu', 'L')
assert d5.set_opponent('nonexistent_char') is None, '未知角色应返回None'
print('✓ 未知对位不猜(返回None)')

# ---- P1-6(审计#6残余): 三处消费方注入生效(真实常量/真实宏库, 不自造布局) ----
# 三个工具本体在独立进程里跑(需游戏), 无法在此端到端; 本段以**与其完全一致
# 的注入口径**驱动同一个 SideDriver / CHAR_POOL_IDX 单源, 证明这些驱动样本
# 的 core[227+池序] 非零 — 等价消费端证据(门禁另以"生效本体"断言钉调用点):
#   attribution_probe : A 侧 opp=char_b;  对手驱动 opp=char_a
#   branch_demo       : 镜像对局 opp=char 本身(同 deck_matchup 口径)
#   danger_reveal     : 逐副本对手风格 pool:<ch>→ch; com→同角色
from train_tm import TMTrainer as _TMT
_POOL = _TMT._CHAR_POOL_IDX


def _inject_ok(char, side, opp_char, name):
    dd = SideDriver(char, side)
    oid = dd.set_opponent(opp_char)
    assert oid is not None and oid == _POOL.get(opp_char), (
        '%s: 注入池序必须与 CHAR_POOL_IDX 同源(%r vs %r)'
        % (name, oid, _POOL.get(opp_char)))
    ss = dd._side_feat(own, opp, w, bul)
    cc = 2 * dd.n_macros
    assert ss[cc + 227 + oid] > 0.5, '%s: core[227+%d] 应=1(实际%.2f)' % (
        name, oid, ss[cc + 227 + oid])
    # 注: `_opp_char`/`_jz1_ids` 的名字查表(_POOL_OPP_NAME 以**游戏ID**为键,
    # 而 _oid 是**池序**)在本测范围外有独立既有偏差, 已另行上报(W2 待裁定);
    # 本测试只钉 task-9 的注入生效本体(one-hot + 池外位派生)。
    assert dd.feat_builder.opp_outside_pool == (
        0.0 if oid in (0, 1, 2) else 1.0), '%s: 池外位派生错' % name
    print('✓ %s: core[227+%d]=1' % (name, oid))


_inject_ok('reimu', 'L', 'sakuya', 'attribution A侧(reimu→sakuya)')
_inject_ok('sakuya', 'R', 'reimu', 'attribution 对手驱动(sakuya→reimu)')
_inject_ok('reimu', 'R', 'reimu', 'branch_demo 镜像(reimu→reimu)')
_inject_ok('reimu', 'L', 'sakuya', 'danger pool:sakuya(逐副本对家)')
_inject_ok('reimu', 'L', 'reimu', 'danger com(同角色)')

print('\nSideDriver语义行为测试通过 ✓')
