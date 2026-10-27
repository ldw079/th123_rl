# -*- coding: utf-8 -*-
"""R15: TH123_BC_DIR 指针切换 (env 优先; 无 env 行为不变)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import bc_io  # noqa: E402
import numpy as np  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    d = tempfile.mkdtemp(prefix='bcdir_')
    base = os.path.join(d, 'bc_test')
    np.save(base + '_X.npy', np.zeros((3, 4), np.uint8))
    np.save(base + '_S.npy', np.zeros((3, 2), np.float32))
    np.save(base + '_Y.npy', np.zeros((3,), np.int64))
    old = os.environ.get('TH123_BC_DIR')
    try:
        os.environ['TH123_BC_DIR'] = d
        kind, b = bc_io.find_bank('test')
        check('TH123_BC_DIR 优先选中新目录', kind == 'trio' and b == base,
              '%s %s' % (kind, b))
    finally:
        if old is None:
            os.environ.pop('TH123_BC_DIR', None)
        else:
            os.environ['TH123_BC_DIR'] = old
    # invalid env → 不静默 fallback(必须找不到, 交回滚)
    old2 = os.environ.get('TH123_BC_DIR')
    try:
        os.environ['TH123_BC_DIR'] = os.path.join(d, '__no_such__')
        kind2, b2 = bc_io.find_bank('test')
        check('invalid env 不 fallback', kind2 in (None,)),
        check('无 env 时 find_bank 不指向临时目录',
              bc_io.find_bank('test')[0] in (None, 'trio', 'npz'))
        os.environ.pop('TH123_BC_DIR', None)
        check('无 env 时 find_bank 不指向临时目录',
              bc_io.find_bank('test')[0] in (None, 'trio', 'npz'))
    finally:
        if old2 is None:
            os.environ.pop('TH123_BC_DIR', None)
        else:
            os.environ['TH123_BC_DIR'] = old2
    print('\n==== bc_dir_env: %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
