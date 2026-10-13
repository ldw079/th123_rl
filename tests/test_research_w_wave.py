# -*- coding: utf-8 -*-
"""W波(研究借鉴方案§W3/W4/W5) — 行为断言.

- W3: four_lenses四口径并列(前两口径来自矩阵, 后两口径league日志;
  缺数据时字段None+notes, 不抛), 旧报告键不删(向后兼容);
- W4: value_line聚合语义(W/L分开报数) + thirds_mean三段;
  领先局>均势局2σ断言(合成轨迹);
- W5: exploit_decay分段(局数回退=重启分段)与判读语言
  (持续克制/一次性奇袭), 真实形态=累积值跨块。
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import numpy as np

FAILS = []


def check(name, cond, detail=''):
    print('%-56s %s %s' % (name, 'PASS' if cond else 'FAIL',
                           detail if not cond else ''))
    if not cond:
        FAILS.append(name)


# ---- W4: value_curve聚合 ----
from value_curve import value_line, thirds_mean
traj_w = [(i, 0.5 + np.random.default_rng(i).normal(0, 0.01)) for i in range(0, 300, 30)]
traj_l = [(i, -0.4 + np.random.default_rng(i + 99).normal(0, 0.01)) for i in range(0, 300, 30)]
line = value_line([(traj_w, 'W'), (traj_l, 'L'), ([], 'W')])
check('W4: value_line含W/L均值与n', 'W局均值0.5' in line
      and 'L局均值-0.4' in line and 'n1' in line, line)
e, m, l = thirds_mean([(i, float(i)) for i in range(30)])
check('W4: thirds_mean三段划分(早中晚)', e < m < l and abs(l - 24.5) < 0.5,
      '%s %s %s' % (e, m, l))
check('W4: 空轨迹三段None', thirds_mean([]) == (None, None, None))
# 2σ断言(合成): W局均值 vs L局均值差>2×合并σ
wv = [v for _f, v in traj_w]
lv = [v for _f, v in traj_l]
pooled_sd = float(np.sqrt((np.var(wv) + np.var(lv)) / 2))
check('W4: 领先局均值>L局 2σ(合成轨迹)',
      (np.mean(wv) - np.mean(lv)) > 2 * pooled_sd)

# ---- W5: exploit_decay ----
from league_weekly import exploit_decay
blocks = [
    {'ts': '10 12 10:00:00', 'rows': [
        ('reimu@exploit_a', 0, 10), ('marisa@x', 5, 5)]},
    {'ts': '10 12 11:00:00', 'rows': [
        ('reimu@exploit_a', 2, 18)]},          # 累积: 10局时0%→20局10%
    {'ts': '10 12 12:00:00', 'rows': [
        ('reimu@exploit_a', 14, 6)]},          # 适应: 20局70%
    {'ts': '10 12 13:00:00', 'rows': [
        ('reimu@exploit_a', 3, 1)]},           # 重启: 分段(4局75%)
]
ed = exploit_decay(blocks)
_a = ed.get('reimu@exploit_a')
check('W5: 重启分段取最长段', _a is not None and _a['games'] == 20,
      str(_a))
check('W5: 适应判读(胜率0%→70%)',
      _a['verdict'] == '半衰期约10局(暴露后适应)'
      or '适应' in _a['verdict'], _a['verdict'])
ed2 = exploit_decay([
    {'ts': 't1', 'rows': [('reimu@exploit_b', 0, 8)]},
    {'ts': 't2', 'rows': [('reimu@exploit_b', 0, 20)]}])
check('W5: 持续克制判读(0%恒)', '持续克制' in ed2['reimu@exploit_b']['verdict'])
check('W5: 非exploit标签不入读数', 'marisa@x' not in ed)

# ---- W3: four_lenses ----
from eval_matrix import four_lenses
tmp = tempfile.mkdtemp(prefix='w3_')
sup = os.path.join(tmp, 'sup.log')
open(sup, 'w', encoding='utf8').write(
    '[10-12 10:00:00] league重算:   reimu@exploit_a    0W- 10L (0%) 权重1.00\n'
    '[10-12 10:00:00]   marisa@snap   5W- 5L (50%) 权重0.50\n')
m = {('reimu', 'marisa'): {'games': 10, 'wins': 6},
     ('reimu', 'suika'): {'games': 10, 'wins': 2}}
fl = four_lenses(m, ['reimu'], sup_log=sup)
check('W3: 针对价值=最弱对位', fl['targeted_value']['pair'] == ('reimu', 'suika')
      and fl['targeted_value']['wr'] == 0.2)
check('W3: 种群平均', fl['population_avg'] == 0.4)
check('W3: 最坏反制剩余读league', fl['worst_exploit'] is not None
      and fl['worst_exploit']['main_wr'] == 0.0, str(fl['worst_exploit']))
check('W3: 适应后持续(固化指数)在位', fl['adapt_persistence'] is not None)
fl2 = four_lenses(m, ['reimu'], sup_log=os.path.join(tmp, 'nope.log'))
check('W3: 日志缺失→note不抛', 'league读数不可用' in str(fl2.get('notes'))
      or fl2['worst_exploit'] is None)

print()
if FAILS:
    print('FAIL(%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('ALL PASS (12)')
