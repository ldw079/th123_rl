# -*- coding: utf-8 -*-
"""S-2迁移: 全部模型档从330→343侧宽(load自动迁移+save新宽)。

- load路径_map_row: 旧330段逐位保持, 新13段(S-2: 变招6+心理4+风格2
  +K5池外1)零初始化 — 旧策略位等价。
- 迁移前整体备份到STORE/backup_330era(回滚=拷回)。
- 只动W_side为330代(5N+330)的档; 343代跳过; 其他宽度跳过并报告。
"""
import glob
import os
import re
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

from ppo import PPOTrainer  # noqa
from feat_builder import FeatureBuilder  # noqa

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
OLD_DIMS, NEW_DIMS = 343, FeatureBuilder.CORE_DIMS
BAK = os.path.join(STORE, 'backup_343era')

CHARS = {'reimu': 70, 'marisa': 76, 'suika': 77}
for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'macros', '[a-z]*.py')):
    m = re.search(r'N_MACROS_\w+ = (\d+)', open(f, encoding='utf8').read())
    if m:
        ch = os.path.basename(f)[:-3]
        if ch not in CHARS:
            CHARS[ch] = int(m.group(1))

assert NEW_DIMS in (343, 358), NEW_DIMS
targets = sorted(glob.glob(os.path.join(STORE, 'model_ppo_*.npz')))
os.makedirs(BAK, exist_ok=True)
migrated = skipped = odd = 0
for p in targets:
    b = os.path.basename(p)
    if '_v' in b or 'tmp' in b:
        continue
    d = np.load(p)
    if 'W_side' not in d.files:
        d.close()
        continue
    w = int(d['W_side'].shape[0])
    n_out = int(d['W2'].shape[1])
    d.close()
    if w == 5 * n_out + NEW_DIMS:
        skipped += 1
        continue
    if w != 5 * n_out + OLD_DIMS:
        print('  %s: %d(非%d也非%d) — 跳过!' % (
            b, w, 5 * n_out + OLD_DIMS, 5 * n_out + NEW_DIMS))
        odd += 1
        continue
    v = p.replace('.npz', '_v.npz')
    if not os.path.exists(v):
        print('  %s: 无v文件 — 跳过!' % b)
        odd += 1
        continue
    for src in (p, v):                       # 备份(存在即不覆盖)
        dst = os.path.join(BAK, os.path.basename(src))
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
    t = PPOTrainer(n_side=5 * n_out + NEW_DIMS, n_out=n_out)
    t.load(p, v)
    t.save(p, v)
    # 迁移后自验: 重读回, 侧宽=新值
    d2 = np.load(p)
    assert int(d2['W_side'].shape[0]) == 5 * n_out + NEW_DIMS, b
    d2.close()
    print('  %s: %d → %d ✓' % (b, w, 5 * n_out + NEW_DIMS))
    migrated += 1

print('\n迁移%d个 跳过%d个(已是%d代) 异常%d个; 备份: %s'
      % (migrated, skipped, NEW_DIMS, odd, BAK))
