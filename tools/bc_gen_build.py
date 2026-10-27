# -*- coding: utf-8 -*-
"""BC gen 目录构建（指针切换用；不写生产）.

用法:
  python tools/bc_gen_build.py --char reimu --anchor <npz3> --outdir D:\temp\bc_gen2
构建 outdir 下 bc_<char>_{X,S,Y,meta.json}（生产 trio + 锚 509 行；full copy，非 rename）,
并写 gen_manifest.json（C1: gen/width/hash/parent/device/status）。
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from bc_anchor_collect import TARGET_KEYS  # noqa: E402
import bc_io  # noqa: E402


def sha_arr(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--anchor', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--store', default=r'D:\temp\th123_models')
    ap.add_argument('--gen', default='gen2')
    a = ap.parse_args()
    base = os.path.join(a.store, 'bc_%s' % a.char)
    X = np.load(base + '_X.npy', mmap_mode='r')
    S = np.load(base + '_S.npy', mmap_mode='r')
    Y = np.load(base + '_Y.npy', mmap_mode='r')
    meta = json.load(open(base + '_meta.json', encoding='utf-8'))
    with np.load(a.anchor, allow_pickle=True) as z:
        AX, AS, AY = z['X'], z['S'], z['Y']
        Asrc = z['src'] if 'src' in z.files else np.array([], dtype=object)
    assert AX.shape[1] == X.shape[1] and AS.shape[1] == S.shape[1]
    nX = np.concatenate([np.asarray(X), AX]).astype(np.uint8)
    nS = np.concatenate([np.asarray(S), AS]).astype(np.float32)
    nY = np.concatenate([np.asarray(Y), AY]).astype(np.int64)
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.join(a.outdir, 'bc_%s' % a.char)
    np.save(out + '_X.npy', nX)
    np.save(out + '_S.npy', nS)
    np.save(out + '_Y.npy', nY)
    nmeta = dict(meta)
    nmeta['rows'] = int(len(nY))
    h = dict(meta.get('hashes') or {})
    h.update({'X': bc_io._arr_sha256(nX), 'S': bc_io._arr_sha256(nS), 'Y': bc_io._arr_sha256(nY)})
    nmeta['hashes'] = h
    # I 列: 生产 I(若存在)+新增唯一 shard id; 与 trio 同宽校验
    ipath = os.path.join(a.store, 'bc_%s_I.npy' % a.char)
    nI = None
    if os.path.exists(ipath):
        I = np.load(ipath, mmap_mode='r')
        if len(I) != len(Y):
            raise SystemExit('prod I rows mismatch')
        nxt = int(I.max()) + 1
        nI = np.concatenate([np.asarray(I),
                             np.arange(nxt, nxt + len(AY), dtype=I.dtype)])
        np.save(out + '_I.npy', nI)
        h['I'] = bc_io._arr_sha256(nI)
    nmeta['gen'] = a.gen
    nmeta['anchor'] = {'npz': os.path.basename(a.anchor),
                       'n_rows': int(len(AY)),
                       'mode': 'pointer-gen'}
    json.dump(nmeta, open(out + '_meta.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    man = {'gen': a.gen, 'char': a.char,
           'parent_store': os.path.abspath(a.store),
           'parent_rows': int(len(Y)), 'rows': int(len(nY)),
           'width_X': int(nX.shape[1]), 'width_S': int(nS.shape[1]),
           'hash_X': sha_arr(nX), 'hash_S': sha_arr(nS), 'hash_Y': sha_arr(nY),
           'anchor': os.path.abspath(a.anchor),
           'anchor_rows': int(len(AY)),
           'status': 'built', 'device': 'cpu',
           'files': {s: sha_file(out + s) for s in
                     ('_X.npy', '_S.npy', '_Y.npy', '_I.npy', '_meta.json')
                     if os.path.exists(out + s)}}
    json.dump(man, open(os.path.join(a.outdir, 'gen_manifest_%s_%s.json'
                                     % (a.gen, a.char)), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({'char': a.char, 'rows': int(len(nY)),
                      'width_S': int(nS.shape[1]), 'out': out,
                      'manifest': os.path.join(a.outdir,
                                               'gen_manifest_%s_%s.json'
                                               % (a.gen, a.char))},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
