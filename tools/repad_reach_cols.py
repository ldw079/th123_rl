# -*- coding: utf-8 -*-
"""R24: BC库追加射程差特征块(末尾+N零列; 历史行无该块=0, 语义=未解析,
与运行时未解析宏的填法一致)。模型侧由load()侧维零行迁移自动对齐。
用法: python tools/repad_reach_cols.py"""
import io
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')
from train_tm import CHAR_LIBS  # noqa: E402

for ch in ('reimu', 'marisa', 'suika'):
    n = len(CHAR_LIBS[ch]['macros'])
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'data', 'bc', 'bc_%s.npz' % ch)
    # R38守卫(第九轮审计P0-6): 带layout版本=bc_build原生5N+308构建 —
    # 零填充只会制造全零gap块(P0-6事故根源), 拒跑。
    import json
    try:
        _meta = json.loads(str(np.load(p, allow_pickle=True)['meta']))
    except Exception:
        _meta = {}
    if isinstance(_meta, dict) and _meta.get('layout'):
        print('%s: 布局%s(原生构建) — 拒绝repad' % (ch, _meta['layout']))
        continue
    d = np.load(p, allow_pickle=False)
    S = d['S']
    want = 5 * n + 308
    if S.shape[1] == want:
        print('%s: 已是%d — 跳过' % (ch, want))
        continue
    bak = p + '.pre2d.bak'
    if not os.path.exists(bak):
        shutil.copy2(p, bak)
    Sn = np.concatenate(
        [S, np.zeros((len(S), want - S.shape[1]), dtype=S.dtype)], axis=1)
    np.savez(p, X=d['X'], Y=d['Y'], S=Sn, C=d['C'])
    print('%s: S %d → %d (备份%s)' % (ch, S.shape[1], Sn.shape[1],
                                      os.path.basename(bak)))
print('射程块repad完成')
