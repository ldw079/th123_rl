# -*- coding: utf-8 -*-
"""task-29/30 统一 mask 层单测(合成状态矩阵)."""
import importlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import game_gates as G  # noqa: E402

FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


NAMES = ['待机', '前进', '后退', '跳跃', '后跳', '前冲', '空冲', '飞翔',
         'jA', 'j6A', 'jC', '5A', '2A', '6A', '立防', '蹲防', '受身',
         '起身', '起身穿', '结界2', '结界4', '空结界4', '卡·铜钱',
         '卡·白楼剑', '卡·药水', '623B', '236B']
N = len(NAMES)


def full():
    return np.ones(N, dtype=bool)


def idx(names):
    return {n: i for i, n in enumerate(names)}


def allowed(m, names=NAMES):
    return {n for i, n in enumerate(names) if m[i]}


def st(action=0, air=False, **kw):
    d = {'action': action, 'airBorne': air}
    d.update(kw)
    return d


print('== task-29/30 unified mask ==')
chk('默认总开关开', G.ACT_MASK and G.AIR_GATE and G.IMMOBILE_GATE)
# 地面
m = G.apply_state_gates(full(), NAMES, st(0, False))
a = allowed(m)
chk('地面: 禁空中专属(jA/空冲/飞翔/空结界4)',
    not ({'jA', 'j6A', 'jC', '空冲', '飞翔', '空结界4'} & a))
chk('地面: 保留地面攻击/防御/移动/待机',
    {'5A', '2A', '立防', '蹲防', '跳跃', '前冲', '后跳', '待机',
     '前进', '后退'} <= a)
chk('地面: 受身放行(§受身 both, 不受 AIR_GATE)', '受身' in a)
chk('地面: 铜钱/白楼剑放行', {'卡·铜钱', '卡·白楼剑'} <= a)
# 空中
m = G.apply_state_gates(full(), NAMES, st(214, True))
a = allowed(m)
chk('空中: 禁地面攻击/防御/DD/起身/后跳',
    not ({'5A', '2A', '6A', '立防', '蹲防', '结界2', '结界4', '起身',
          '后跳'} & a))
chk('空中: 保留空中攻击/空冲/飞翔/待机/受身',
    {'jA', 'j6A', 'jC', '空冲', '飞翔', '待机', '受身'} <= a)
# 正防硬直
a = allowed(G.apply_state_gates(full(), NAMES, st(155, False)))
chk('150-157: 放 DD/铜钱/白楼剑/防御切换',
    {'结界2', '结界4', '卡·铜钱', '卡·白楼剑', '立防',
     '蹲防'} <= a)
chk('150-157: 禁攻击/移动',
    not ({'5A', '2A', 'jA', '跳跃', '前冲', '待机'} & a))
# 158 / 159-166
chk('158(空防硬直): 全 mask→仅待机',
    allowed(G.apply_state_gates(full(), NAMES, st(158, False))) == {'待机'})
chk('159-166(错防): 全 mask→仅待机',
    allowed(G.apply_state_gates(full(), NAMES, st(163, False))) == {'待机'})
# 受创/倒地
chk('受创50-78: 只放受身',
    allowed(G.apply_state_gates(full(), NAMES, st(60, False))) == {'受身'})
chk('倒地88: 只放受身/起身/起身穿',
    allowed(G.apply_state_gates(full(), NAMES, st(88, False))) ==
    {'受身', '起身', '起身穿'})
# env=0 逐位
os.environ['TH123_ACT_MASK'] = '0'
importlib.reload(G)
m0 = full()
chk('env=0: 原样返回(逐位)', np.array_equal(
    G.apply_state_gates(m0, NAMES, st(163, False)), m0))
os.environ['TH123_ACT_MASK'] = '1'
importlib.reload(G)
# 空 mask → 仅待机(去掉待机宏应响亮报错)
_no_idle = [n for n in NAMES if n != '待机']
mask_no_idle = np.zeros(len(_no_idle), dtype=bool)
try:
    G.apply_state_gates(mask_no_idle, _no_idle, st(163, False))
    chk('无待机宏时响亮报错', False)
except RuntimeError:
    chk('无待机宏时响亮报错', True)
print('==== task-29/30 mask: %d PASS / %d FAIL ===='
      % (19 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
