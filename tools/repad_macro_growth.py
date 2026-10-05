# -*- coding: utf-8 -*-
"""R23: 宏数增长重铺垫(单角色) — BC库S列插入新宏one-hot零列 +
宏计数数组扩展(新宏计数0=配额探针自动接管)。
S布局[宏N][上宏N][core]: 每块尾插零列。
用法: python tools/repad_macro_growth.py suika 63 64"""
import io
import os
import shutil
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ch, n_old, n_new = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
assert n_new >= n_old
if n_new == n_old:
    print('%s: 宏数未变 — 无需处理' % ch)
    sys.exit(0)

# 1) BC库
p = os.path.join(ROOT, 'data', 'bc', 'bc_%s.npz' % ch)
# R38守卫(第九轮审计P0-6): 带layout版本=bc_build原生构建, 且本脚本
# 只补one-hot块不补尾部gap/untech块(5N布局下会错位) — 拒跑, 请重建。
import json
try:
    _meta = json.loads(str(np.load(p, allow_pickle=True)['meta']))
except Exception:
    _meta = {}
if isinstance(_meta, dict) and _meta.get('layout'):
    print('BC库 %s: 布局%s(原生构建) — 拒绝repad, 请重跑bc_build' % (
        ch, _meta['layout']))
else:
    d = np.load(p, allow_pickle=False)
    S = d['S']
    core_w = S.shape[1] - 2 * n_old
    assert core_w > 0, 'S宽度与旧宏数不符: %d' % S.shape[1]
    Sn = np.concatenate([S[:, :n_old],
                         np.zeros((len(S), n_new - n_old), dtype=S.dtype),
                         S[:, n_old:2 * n_old],
                         np.zeros((len(S), n_new - n_old), dtype=S.dtype),
                         S[:, 2 * n_old:]], axis=1)
    bak = p + '.mg%d.bak' % n_old
    if not os.path.exists(bak):
        shutil.copy2(p, bak)
    np.savez(p, X=d['X'], Y=d['Y'], S=Sn, C=d['C'])
    print('BC库 %s: S %d → %d (备份%s)'
          % (ch, S.shape[1], Sn.shape[1], os.path.basename(bak)))

# 2) 宏计数(所有路径变体: 主线+suffix)
import glob
for mp in glob.glob(os.path.join(r'D:\temp\th123_models',
                                 'macro_counts_%s*.npy' % ch)):
    mc = np.load(mp)
    if len(mc) >= n_new:
        print('  宏计数 %s: 已%d — 跳过' % (os.path.basename(mp), len(mc)))
        continue
    ext = np.zeros(n_new, dtype=mc.dtype)
    ext[:len(mc)] = mc
    shutil.copy2(mp, mp + '.bak')
    np.save(mp, ext)
    print('  宏计数 %s: %d → %d' % (os.path.basename(mp), len(mc), n_new))
print('宏数增长重铺垫完成(%s %d→%d)' % (ch, n_old, n_new))
