# -*- coding: utf-8 -*-
"""B迁移: 全部模型档从316→330侧宽(load自动迁移+save新宽)。"""
import glob
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

from ppo import PPOTrainer  # noqa
from feat_builder import FeatureBuilder  # noqa

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
OLD_DIMS, NEW_DIMS = 316, 330

# 角色宏数
CHARS = {'reimu': 70, 'marisa': 76, 'suika': 77}
# 新角色(未训练, 模型可能不存在)
for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'macros_*.py')):
    import re
    src = open(f, encoding='utf-8').read()
    m = re.search(r'N_MACROS_\w+ = (\d+)', src)
    if m:
        ch = os.path.basename(f)[7:-3]
        if ch not in CHARS:
            CHARS[ch] = int(m.group(1))

migrated = skipped = 0
for p in sorted(glob.glob(os.path.join(STORE, 'model_ppo_*.npz'))):
    if '_v' in os.path.basename(p) or 'tmp' in p:
        continue
    d = np.load(p)
    if 'W_side' not in d.files:
        d.close()
        continue
    w = int(d['W_side'].shape[0])
    n_out = int(d['W2'].shape[1])
    d.close()
    if w == 5 * n_out + NEW_DIMS:
        print('  %s: 已%d — 跳过' % (os.path.basename(p), w))
        skipped += 1
        continue
    if w != 5 * n_out + OLD_DIMS:
        print('  %s: %d(非%d也非%d) — 跳过' % (
            os.path.basename(p), w, 5*n_out+OLD_DIMS, 5*n_out+NEW_DIMS))
        continue
    v = p.replace('.npz', '_v.npz')
    if not os.path.exists(v):
        print('  %s: 无v文件 — 跳过' % os.path.basename(p))
        continue
    t = PPOTrainer(n_side=5 * n_out + NEW_DIMS, n_out=n_out)
    t.load(p, v)
    t.save(p, v)
    print('  %s: %d → %d ✓' % (os.path.basename(p), w, t.N_SIDE))
    migrated += 1

print('\n迁移%d个 跳过%d个' % (migrated, skipped))
