# -*- coding: utf-8 -*-
"""bc_meta_resync.py — 迁移/换代后重算 BC trio meta 哈希(修复 S 哈希≠meta).

用法: python tools/bc_meta_resync.py [--dry] [--store D:\\temp\\th123_models]
仅重算 X/S/Y/I 内容哈希与 layout, 不改数组内容; 先备份 meta 到 *.bak.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def resync(base, dry=False):
    import bc_io
    mp = base + '_meta.json'
    meta = json.load(open(mp, encoding='utf8'))
    hs = dict(meta.get('hashes') or {})
    for k in ('X', 'S', 'Y', 'I'):
        fp = base + '_%s.npy' % k
        if not os.path.exists(fp):
            continue
        hs[k] = bc_io._arr_sha256(np.load(fp, mmap_mode='r'))
    meta['hashes'] = hs
    print('[resync] %s hashes=%s' % (os.path.basename(base), hs))
    if dry:
        return 0
    shutil.copy2(mp, mp + '.bak')
    tmp = mp + '.tmp'
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, mp)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--store', default=r'D:\temp\th123_models')
    ap.add_argument('--chars', default='reimu,marisa,suika')
    a = ap.parse_args()
    n = 0
    for ch in a.chars.split(','):
        base = os.path.join(a.store, 'bc_%s' % ch)
        if os.path.exists(base + '_meta.json'):
            resync(base, dry=a.dry)
            n += 1
    print('[done] %d 库' % n)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
