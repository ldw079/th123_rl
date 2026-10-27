# -*- coding: utf-8 -*-
"""C15: gen meta hash 16hex 必需; 64hex 拒; gen build I/loader."""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import bc_io  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def mkstore(store, rows=20):
    base = os.path.join(store, 'bc_test')
    np.save(base + '_X.npy', np.zeros((rows, 4), np.uint8))
    np.save(base + '_S.npy', np.zeros((rows, 3), np.float32))
    np.save(base + '_Y.npy', np.zeros((rows,), np.int64))
    np.save(base + '_I.npy', np.arange(rows, dtype=np.int64))
    meta = {'n_macros': 10, 'rows': rows, 'hashes': {
        'X': bc_io._arr_sha256(np.load(base + '_X.npy')),
        'S': bc_io._arr_sha256(np.load(base + '_S.npy')),
        'Y': bc_io._arr_sha256(np.load(base + '_Y.npy')),
        'I': bc_io._arr_sha256(np.load(base + '_I.npy'))}}
    json.dump(meta, open(base + '_meta.json', 'w'))
    return base


def main():
    d = tempfile.mkdtemp(prefix='genhash_')
    st = os.path.join(d, 'store')
    os.makedirs(st)
    base = mkstore(st)
    os.environ['TH123_BC_DIR'] = st
    try:
        X, S, Y = bc_io.load_bank('test', verify=True)
        check('16hex meta: loader PASS', len(Y) == 20)
    except Exception as e:
        check('16hex meta: loader PASS', False, repr(e)[:100])
    meta = json.load(open(base + '_meta.json'))
    meta['hashes']['Y'] = 'a' * 64
    json.dump(meta, open(base + '_meta.json', 'w'))
    rejected = False
    try:
        bc_io.load_bank('test', verify=True)
    except Exception:
        rejected = True
    check('64hex meta: loader 拒绝', rejected)
    # separate store/gen for build (avoid overwriting mmap'd files)
    st2 = os.path.join(d, 'store2')
    os.makedirs(st2)
    base2 = mkstore(st2)
    an = os.path.join(d, 'anchor.npz')
    np.savez(an, X=np.ones((5, 4), np.uint8), S=np.ones((5, 3), np.float32),
             Y=np.ones((5,), np.int64),
             src=np.array([['a', 'b', 'c', 'd'] for _ in range(5)],
                          dtype=object))
    gen = os.path.join(d, 'gen')
    r = subprocess.run([sys.executable, '-X', 'utf8',
                        os.path.join(ROOT, 'tools', 'bc_gen_build.py'),
                        '--char', 'test', '--anchor', an, '--outdir', gen,
                        '--store', st2, '--gen', 'gen2'],
                       capture_output=True, text=True, timeout=120)
    check('gen build rc=0', r.returncode == 0, r.stderr[-100:])
    try:
        X, S, Y = bc_io.load_bank('test', dirs=[gen], verify=True)
        X2, S2, Y2, I = bc_io.load_bank_seq('test', dirs=[gen])
        check('gen 16hex + loader PASS', len(Y) == 25 and I is not None)
    except Exception as e:
        check('gen 16hex + loader PASS', False, repr(e)[:100])
    print('\n==== bc_gen_meta_hash: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
