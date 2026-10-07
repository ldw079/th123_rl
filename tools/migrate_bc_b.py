# -*- coding: utf-8 -*-
"""B迁移: BC库316→330(S列core段尾插14零列)。"""
import glob
import io
import json
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD, NEW = 316, 330

for p in sorted(glob.glob(os.path.join(ROOT, 'data', 'bc', 'bc_*.npz'))):
    if '.bak' in os.path.basename(p) or '.tmp' in os.path.basename(p):
        continue
    d = np.load(p, allow_pickle=True)
    S = d['S']
    n = None
    # 推宏数: S宽 = 5N + core → N = (S宽-core)/5
    old_w = S.shape[1]
    if old_w % 5 == NEW % 5:  # 粗检已迁移
        n_check = (old_w - NEW) // 5
        if old_w == 5 * n_check + NEW:
            print('%s: 已%d(=5*%d+%d) — 跳过' % (
                os.path.basename(p), old_w, n_check, NEW))
            d.close()
            continue
    n = (old_w - OLD) // 5
    assert old_w == 5 * n + OLD, \
        '%s: S宽%d≠5*%d+%d' % (p, old_w, n, OLD)
    meta = {}
    if 'meta' in d.files:
        try:
            meta = json.loads(str(d['meta']))
        except Exception:
            pass
    # S布局[宏N][上宏N][core OLD][gap N][gap_v N][untech N]
    # → core段尾插14零列: [宏N][上宏N][core NEW][gap N][gap_v N][untech N]
    Sn = np.concatenate([
        S[:, :2 * n + OLD],                    # 前段(含旧core)
        np.zeros((len(S), NEW - OLD), dtype=S.dtype),  # B新增14列
        S[:, 2 * n + OLD:],                    # 尾三块
    ], axis=1)
    # meta layout更新
    if isinstance(meta, dict) and 'layout' in meta:
        meta['layout'] = '5N+%d:v2' % NEW
    bak = p + '.core%d.bak' % OLD
    if not os.path.exists(bak):
        shutil.copy2(p, bak)
    np.savez(p, X=d['X'], Y=d['Y'], S=Sn, C=d['C'],
             meta=np.array(json.dumps(meta)))
    d.close()
    print('%s: S %d → %d ✓ (宏%d, 备份%s)'
          % (os.path.basename(p), old_w, Sn.shape[1], n,
             os.path.basename(bak)))
print('BC库B迁移完成')
