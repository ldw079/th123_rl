# -*- coding: utf-8 -*-
"""S-6行为测试: BC序列感知采样 — shard组id/连续窗口语义/保序/往返/
旧库回落iid。"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from bc_io import load_bank_seq, npz_to_trio, sample_seq_window

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    rng = np.random.default_rng(7)

    # ===== sample_seq_window单元 =====
    # I: 组0×5行, 组1×3行, 组2×10行(同id相邻)
    I = np.array([0]*5 + [1]*3 + [2]*10)
    # 窗口采样: 同组连续
    for _ in range(30):
        w = sample_seq_window(I, 4, rng)
        check_id = I[w]
        check('窗口同组', (check_id == check_id[0]).all())
        check('窗口连续', (np.diff(w) == 1).all())
        check('窗口长≤k', len(w) <= 4)
    # 短组(3<k=4): 整组3行
    w3 = sample_seq_window(np.array([9]*3), 4, rng)
    check('短组取整组', len(w3) == 3 and (np.diff(w3) == 1).all())
    # None → None(回落语义)
    check('I=None回落', sample_seq_window(None, 4, rng) is None)

    # ===== npz→trio→load_bank_seq往返 =====
    tmp = tempfile.mkdtemp(prefix='bc_seq_')
    try:
        n = 20
        X = np.arange(n * 8, dtype=np.uint8).reshape(n, 8)
        S = np.arange(n * 4, dtype=np.float32).reshape(n, 4)
        Y = (np.arange(n) % 3).astype(np.int64)
        Icol = np.array([1]*10 + [2]*10)
        p = os.path.join(tmp, 'bc_testchar.npz')
        np.savez(p, X=X, S=S, Y=Y, C=np.zeros(n, dtype=np.float32),
                 I=Icol, meta=np.array('{"char":"testchar"}'))
        npz_to_trio(p)
        X2, S2, Y2, I2 = load_bank_seq('testchar', dirs=[tmp])
        check('trio往返X', np.array_equal(np.asarray(X2), X))
        check('trio往返I', np.array_equal(np.asarray(I2), Icol))
        # 旧库(无I) → I=None
        p_old = os.path.join(tmp, 'bc_oldchar.npz')
        np.savez(p_old, X=X, S=S, Y=Y,
                 meta=np.array('{"char":"oldchar"}'))
        npz_to_trio(p_old)
        X3, S3, Y3, I3 = load_bank_seq('oldchar', dirs=[tmp])
        check('旧库I=None(回落iid)', I3 is None and X3 is not None)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
