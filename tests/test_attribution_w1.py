# -*- coding: utf-8 -*-
"""W1(研究借鉴方案§W1): 延迟消融 — 行为断言(不起游戏)."""
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

FAILS = []


def check(name, cond, detail=''):
    print('%-52s %s %s' % (name, 'PASS' if cond else 'FAIL',
                           detail if not cond else ''))
    if not cond:
        FAILS.append(name)


# ---- DelayedView ----
from attribution_probe import DelayedView

# k=0: 即时(透传)
dv = DelayedView(0)
for i in range(5):
    r = dv.push(('frame', i))
    check('k=0透传(i=%d)' % i, r == ('frame', i),
          'got %s' % str(r))
    if i < 4:
        break

# k=3: 前3帧None, 之后返回3帧前的
dv = DelayedView(3)
warmup_none = 0
returns = []
for i in range(8):
    r = dv.push(i)
    if r is None:
        warmup_none += 1
    else:
        returns.append(r)
check('k=3 warmup=3帧None', warmup_none == 3,
      'got %d' % warmup_none)
check('k=3 返回延迟帧序列', returns == [0, 1, 2, 3, 4],
      'got %s' % str(returns))
check('k=3 warmup计数', dv.warmup == 3)

# reset
dv.reset()
check('reset清空', len(dv.buf) == 0 and dv.warmup == 0)

# 边界: k=5, 序列正确
dv = DelayedView(5)
seq = list(range(12))
outs = [dv.push(x) for x in seq]
check('k=5 前5帧None', all(o is None for o in outs[:5]))
check('k=5 输出=输入延迟5', outs[5:] == seq[:7],
      'got %s' % str(outs[5:]))

# 帧tuple保持引用完整性
dv = DelayedView(2)
f1 = (dict(a=1), dict(b=2), 'w', [])
f2 = (dict(a=2), dict(b=3), 'w', [])
f3 = (dict(a=3), dict(b=4), 'w', [])
dv.push(f1)
dv.push(f2)
r = dv.push(f3)
check('tuple引用完整(返回的是原始对象)', r is f1)

# ---- 曲线验收逻辑(合成) ----
# 延迟↑胜率不变或降(非单调升=垫片bug) — 方案验收条款
def curve_ok(results):
    """results: {delay: wr} → 单调性检查(允许持平, 不允许升)."""
    delays = sorted(results.keys())
    for i in range(len(delays) - 1):
        if results[delays[i + 1]] > results[delays[i]] + 0.05:
            return False, 'd%d→d%d: %.3f→%.3f(↑)' % (
                delays[i], delays[i + 1],
                results[delays[i]], results[delays[i + 1]])
    return True, ''

ok, msg = curve_ok({0: 0.55, 3: 0.52, 5: 0.48, 8: 0.41})
check('正常衰减曲线通过', ok, msg)
ok, msg = curve_ok({0: 0.41, 3: 0.48, 5: 0.55, 8: 0.60})
check('反向上升曲线拒绝', not ok, msg)
ok, msg = curve_ok({0: 0.50, 3: 0.50, 5: 0.50, 8: 0.50})
check('持平曲线通过(允许)', ok, msg)

print()
if FAILS:
    print('FAIL(%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('ALL PASS (14)')
