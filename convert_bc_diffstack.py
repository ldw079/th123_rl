# -*- coding: utf-8 -*-
"""R19: 既有BC库视觉栈变换 3×原始帧 → [f2, Δ1, Δ2](与train_tm同构)。
原始帧完整保留在库的X列里(14400=3×4800), 可无损转换, 无需重提神谕数据。
公式与train_tm._visual_feat逐字一致: Δ1=clip(f2-f1), Δ2=clip(f1-f0)。
用法: python convert_bc_diffstack.py   (自动备份.bak_prediff)"""
import io
import os
import shutil
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf8')
BC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'data', 'bc')
FW = 60 * 80   # 4800


def convert(X):
    f0 = X[:, 0 * FW:1 * FW].astype(np.int16)
    f1 = X[:, 1 * FW:2 * FW].astype(np.int16)
    f2 = X[:, 2 * FW:3 * FW].astype(np.int16)
    d1 = np.clip(f2 - f1, 0, 255).astype(np.uint8)
    d2 = np.clip(f1 - f0, 0, 255).astype(np.uint8)
    return np.concatenate([f2.astype(np.uint8), d1, d2], axis=1)


for fn in sorted(os.listdir(BC_DIR)):
    if not fn.endswith('.npz') or fn.endswith('.bak') \
            or '.r16.' in fn or '.prediff.' in fn:
        continue
    p = os.path.join(BC_DIR, fn)
    d = np.load(p, allow_pickle=False)
    X = d['X']
    if X.ndim != 2 or X.shape[1] != 3 * FW:
        print('%s: 非原始3帧布局(%s) — 跳过' % (fn, X.shape))
        continue
    # 幂等探测: 已是差分栈则第2通道常为0占比高? 不可靠 — 靠备份命名判断
    bak = p.replace('.npz', '.prediff.bak.npz')
    if os.path.exists(bak):
        print('%s: 已转换(备份在) — 跳过' % fn)
        continue
    Xn = convert(X)
    shutil.copy2(p, bak)
    np.savez(p, X=Xn, Y=d['Y'], S=d['S'], C=d['C'])
    # 差分健康度: 非零像素占比(全零=帧间完全静止=可疑)
    _nz = float((Xn[:, FW:2 * FW] > 0).mean())
    print('%s: %d行已变换(Δ1非零率%.1f%%, 备份%s)'
          % (fn, len(Xn), _nz * 100, os.path.basename(bak)))
print('BC库差分栈变换完成')
