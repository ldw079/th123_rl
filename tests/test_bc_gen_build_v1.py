# -*- coding: utf-8 -*-
"""R15: bc_gen_build 指针 gen 构建（fake store，无生产写）."""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    d = tempfile.mkdtemp(prefix='genb_')
    st = os.path.join(d, 'store')
    os.makedirs(st)
    base = os.path.join(st, 'bc_test')
    np.save(base + '_X.npy', np.zeros((20, 4), np.uint8))
    np.save(base + '_S.npy', np.zeros((20, 3), np.float32))
    np.save(base + '_Y.npy', np.zeros((20,), np.int64))
    json.dump({'n_macros': 10, 'rows': 20, 'hashes': {}},
              open(base + '_meta.json', 'w'))
    an = os.path.join(d, 'anchor.npz')
    np.savez(an, X=np.ones((5, 4), np.uint8), S=np.ones((5, 3), np.float32),
             Y=np.ones((5,), np.int64),
             src=np.array([['a', 'b', 'c', 'd'] for _ in range(5)],
                          dtype=object))
    out = os.path.join(d, 'gen2')
    r = subprocess.run([PY, '-X', 'utf8',
                        os.path.join(ROOT, 'tools', 'bc_gen_build.py'),
                        '--char', 'test', '--anchor', an, '--outdir', out,
                        '--store', st, '--gen', 'gen2'],
                       capture_output=True, text=True, timeout=120)
    check('gen_build exit=0', r.returncode == 0, r.stderr[-120:])
    X = np.load(os.path.join(out, 'bc_test_X.npy'))
    S = np.load(os.path.join(out, 'bc_test_S.npy'))
    check('gen rows=20+5', X.shape[0] == 25, str(X.shape))
    check('gen width S', S.shape[1] == 3)
    man = json.load(open(os.path.join(out, 'gen_manifest_gen2_test.json')))
    check('manifest C1 字段', all(k in man for k in
          ('gen', 'rows', 'width_X', 'width_S', 'hash_X', 'status')))
    check('manifest status=built/rows', man['status'] == 'built'
          and man['rows'] == 25)
    check('生产 fake trio 未变', np.load(base + '_X.npy').shape[0] == 20)
    print('\n==== bc_gen_build: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
