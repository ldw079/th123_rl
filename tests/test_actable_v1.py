# -*- coding: utf-8 -*-
"""task-30 C15: actable 状态估计."""
import importlib
import os
import sys

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
os.chdir(WT)
FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


print('== actable v1 ==')
os.environ['TH123_ACTABLE'] = '1'
import actable_state as A  # noqa: E402
importlib.reload(A)
chk('env ACTABLE=1', bool(A.ACTABLE))
t = A.ActableTracker()
f0 = t.update(0)
chk('非 stun: actable=1 est=0', f0['actable'] == 1 and f0['est_left'] == 0)
feats = [t.update(60) for _ in range(6)]
chk('stun 帧累计', feats[-1]['frames_in_stun'] == 6 and t.in_stun)
f1 = t.update(0)
chk('解硬直: 记录 last_len=6', t.last_len == 6 and f1['actable'] == 1)
chk('avg 更新', abs(t.avg_len - 6.0) < 1e-6)
# 第二轮: 第 5 帧 near_end(avg6 → left=1 <=2)
for _ in range(5):
    t.update(60)
f2 = t.update(60)
chk('near_end 最后 2F', f2['near_end'] == 1)
chk('line 格式', '[actable] in_stun=' in t.line())
os.environ['TH123_ACTABLE'] = '0'
importlib.reload(A)
chk('env=0 关闭', not A.ACTABLE)
src = open(os.path.join(WT, 'train_tm.py'), encoding='utf8').read()
chk('train_tm 接线 self._actable', 'self._actable' in src
    and '_actable_mod.ActableTracker()' in src)
print('==== actable v1: %d PASS / %d FAIL ====' % (10 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
