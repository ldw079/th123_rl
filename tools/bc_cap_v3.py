# -*- coding: utf-8 -*-
"""BC v3库行数封顶后处理(2026-10-14内存事故预防).

v3.4匹配器行回收×5 → 单库5.2G; learner load_bc_bank全量驻留
(npz不支持mmap) → 3字符×5.2G顶爆32G机。对已落盘的v3库做
标签比例分层采样到BC_MAX_ROWS(默认10万行), 原子重写。
分布统计(各标签占比)数学期望不变。

用法: python tools/bc_cap_v3.py [--dir D:\\temp\\th123_bc_v3]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def cap_file(p, max_rows):
    size0 = os.path.getsize(p)
    d = np.load(p, allow_pickle=True)
    X, S, Y, C = d['X'], d['S'], d['Y'], d['C']
    meta = json.loads(str(d['meta']))
    if len(Y) <= max_rows:
        print('%s: %d行 ≤ 上限, 跳过' % (os.path.basename(p), len(Y)))
        return
    rng = np.random.default_rng(4321)
    sel = np.zeros(len(Y), dtype=bool)
    for lab in np.unique(Y):
        li = np.where(Y == lab)[0]
        k = max(1, int(round(len(li) * max_rows / len(Y))))
        sel[rng.choice(li, size=min(k, len(li)), replace=False)] = True
    meta['capped_from'] = int(len(Y))
    d.close()   # Windows: 打开的npz句柄锁文件, 关闭后才能原子替换
    tmp = p + '.tmp.npz'
    np.savez(tmp, X=X[sel].astype(np.uint8), S=S[sel], Y=Y[sel],
             C=C[sel], meta=np.array(json.dumps(meta)))
    os.replace(tmp, p)
    print('%s: %d→%d行(%.1fG→%.1fG)' % (
        os.path.basename(p), len(Y), int(sel.sum()),
        size0 / 1e9, os.path.getsize(p) / 1e9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=r'D:\temp\th123_bc_v3')
    ap.add_argument('--max-rows', type=int,
                    default=int(os.environ.get('BC_MAX_ROWS', '100000')))
    a = ap.parse_args()
    for fn in ('bc_reimu_v3.npz', 'bc_marisa_v3.npz', 'bc_suika_v3.npz'):
        p = os.path.join(a.dir, fn)
        if os.path.exists(p):
            cap_file(p, a.max_rows)


if __name__ == '__main__':
    main()
