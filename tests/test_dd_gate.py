# -*- coding: utf-8 -*-
"""task-28 单测: DD(回避结界)仅正防态可用门控."""
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


print('== task-28 dd gate ==')
chk('默认开(guard_only=1)', G.DD_GUARD_ONLY)
chk('guard 边界: 149=False', not G.is_guard_action(149))
chk('guard 边界: 150=True', G.is_guard_action(150))
chk('guard 边界: 167=True', G.is_guard_action(167))
chk('guard 边界: 168=False', not G.is_guard_action(168))
chk('DD 识别: 结界2/4/6/空结界4', all(
    G.is_dd_macro(n) for n in ('结界2', '结界4', '结界6', '空结界4')))
chk('DD 识别: 非 DD 宏不误伤', not any(
    G.is_dd_macro(n) for n in ('前冲', '后冲', '空冲', '超结界破')))

names = ['前冲', '结界2', '结界4', '2A', '空结界4']
mask = np.array([True, True, True, True, True])
non_guard = G.dd_gate(mask, names, 10)
chk('非防态: DD 被 mask', not non_guard[1] and not non_guard[2]
    and not non_guard[4])
chk('非防态: 其它宏保持', non_guard[0] and non_guard[3])
chk('非防态: 输入 mask 不被修改', bool(mask.all()))
guard = G.dd_gate(mask, names, 152)
chk('正防态: 全保持', bool(guard.all()))

os.environ['TH123_DD_GUARD_ONLY'] = '0'
importlib.reload(G)
chk('关闭: DD_GUARD_ONLY=0', not G.DD_GUARD_ONLY)
chk('关闭: 非防态也保持', bool(G.dd_gate(mask, names, 10).all()))
os.environ['TH123_DD_GUARD_ONLY'] = '1'
importlib.reload(G)

line = G.startup_line()
chk('启动行含 mask/dd 开关', ('dd_guard=1' in line or 'guard_only=1' in line)
    and ('[act_mask]' in line or '[dd_gate]' in line))
TOTAL = 14
print('==== task-28 dd gate: %d PASS / %d FAIL ===='
      % (TOTAL - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
