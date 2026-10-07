# -*- coding: utf-8 -*-
"""B动工前侦察: repad工具/hand消费/CORE_DIMS引用面。"""
import glob
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf8')

print('== repad工具 ==')
for f in glob.glob('tools/*.py') + glob.glob('*.py'):
    src = io.open(f, encoding='utf-8', errors='ignore').read()
    if 'repad' in src.lower():
        print(' ', f)

print()
print('== feat_builder: hand消费点 ==')
src = io.open('feat_builder.py', encoding='utf-8').read().splitlines()
for i, l in enumerate(src, 1):
    if 'hand' in l.lower():
        print('%4d: %s' % (i, l.strip()[:95]))

print()
print('== CORE_DIMS引用面 ==')
for f in ['train_tm.py', 'side_driver.py', 'learner_hub.py',
          'bc_build.py', 'teach.py', 'tools/contract_check.py',
          'exploiter.py', 'actor_worker.py']:
    if not os.path.exists(f):
        continue
    src = io.open(f, encoding='utf-8', errors='ignore').read()
    n = len(re.findall(r'CORE_DIMS', src))
    if n:
        print('  %-24s ×%d' % (f, n))

print()
print('== 现存模型宽度盘点(待迁移面) ==')
import numpy as np
pats = [r'D:\temp\th123_models\model_ppo_*.npz',
        r'D:\temp\th123_models\battle\bc_*.npz']
n316 = nother = 0
for p in glob.glob(r'D:\temp\th123_models\model_ppo_*.npz'):
    if 'tmp' in p:
        continue
    d = np.load(p)
    w = int(d['W_side'].shape[0])
    d.close()
    if w % 5 == 316 % 5 or True:
        pass
    n316 += (w > 0)
print('model_ppo_*: %d个' % len(
    [p for p in glob.glob(r'D:\temp\th123_models\model_ppo_*.npz')]))
print('fleet snap: %d个' % len(
    glob.glob(r'D:\temp\th123_models\fleet\snap_*\v*.npz')))
print('fleet pool: %d个' % len(
    glob.glob(r'D:\temp\th123_models\fleet\pool\*\*.npz')))
print('BC banks(data/bc): %d个' % len(glob.glob('data/bc/bc_*.npz')))
