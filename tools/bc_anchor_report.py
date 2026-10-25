# -*- coding: utf-8 -*-
"""task-60 QC 报告: anchor npz 校验/分布/严格复验统计 + 与生产 BC 对比."""
import glob
import io
import json
import os
import sys

import numpy as np

ANCHOR = r'D:\temp\th123_anchor'
STORE = r'D:\temp\th123_models'
OUT = r'D:\temp\scratch\bc_anchor_qc_20261026.md'


def main():
    L = ['# BC 补锚 QC 报告（task-60，2026-10-25）', '']
    total = 0
    for ch in ('reimu', 'marisa', 'suika'):
        npzs = sorted(glob.glob(os.path.join(ANCHOR,
                                             'bc_anchor_%s_*.npz' % ch)))
        if not npzs:
            L.append('- %s: **未生成**' % ch)
            continue
        p = npzs[-1]
        mf = sorted(glob.glob(os.path.join(
            ANCHOR, 'manifest_%s_*.json' % ch)))[-1:]
        m = json.load(io.open(mf[0], encoding='utf-8')) if mf else {}
        with np.load(p, allow_pickle=True) as z:
            X, S, Y = z['X'], z['S'], z['Y']
            src = z['src'] if 'src' in z.files else []
        prodX = np.load('%s/bc_%s_X.npy' % (STORE, ch), mmap_mode='r')
        prodS = np.load('%s/bc_%s_S.npy' % (STORE, ch), mmap_mode='r')
        prodY = np.load('%s/bc_%s_Y.npy' % (STORE, ch), mmap_mode='r')
        ok = (X.shape[1] == prodX.shape[1] and S.shape[1] == prodS.shape[1]
              and Y.max() < int(np.load('%s/bc_%s_Y.npy' % (STORE, ch),
                                        mmap_mode='r').max()) + 1)
        strict = 0
        dmg = []
        for s in src:
            try:
                d = json.loads(str(s))
                if d.get('dmg', 0) >= 300 or len(d.get('acts') or []) >= 2:
                    strict += 1
                dmg.append(float(d.get('dmg', 0)))
            except Exception:
                pass
        per = {int(k): int(v) for k, v in zip(*np.unique(Y, return_counts=True))}
        L.append('## %s' % ch)
        L.append('- npz: `%s`（%d 行; X %s; S %s）'
                 % (os.path.basename(p), len(Y), X.shape, S.shape))
        L.append('- 与生产 trio: X宽 %d==%d; S宽 %d==%d; Y范围 [%d,%d]（n_macros=%s）'
                 % (X.shape[1], prodX.shape[1], S.shape[1], prodS.shape[1],
                    Y.min(), Y.max(), m.get('n_macros')))
        L.append('- 严格复验(采集时): **%d/%d = %.2f**; dmg mean=%.1f max=%.0f'
                 % (strict, len(src), strict / max(1, len(src)),
                    float(np.mean(dmg)) if dmg else 0,
                    float(np.max(dmg)) if dmg else 0))
        L.append('- 每宏行数: ' + ', '.join('%s:%d' % (k, v)
                                           for k, v in sorted(per.items())))
        L.append('- 生产 BC %d 行 → 合并后 %d 行（+%.2f%%）'
                 % (len(prodY), len(prodY) + len(Y),
                    100.0 * len(Y) / max(1, len(prodY))))
        if not ok:
            L.append('- **WARN: 布局校验失败**')
        total += len(Y)
    L.append('')
    L.append('总计锚行: %d' % total)
    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('[written]', OUT)
    print('\n'.join(L))


if __name__ == '__main__':
    main()
