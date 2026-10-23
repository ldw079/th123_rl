# -*- coding: utf-8 -*-
"""bc_io行为测试(2026-10-14用户裁定mmap方案):

trio三件套mmap加载(memmap类型/按页)/64行抽样等值/npz回退兼容/
trio优先级/npz_to_trio转换(含可选封顶与out_stem)。
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

os.environ['TH123_BC_HASH_CACHE'] = '0'   # 篡改检测测试: 关缓存

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from bc_io import find_bank, load_bank, npz_to_trio   # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    tmp = tempfile.mkdtemp(prefix='bcio_')
    rng = np.random.default_rng(7)
    X0 = rng.integers(0, 255, (500, 40)).astype(np.uint8)
    S0 = rng.standard_normal((500, 6)).astype(np.float32)
    Y0 = rng.integers(0, 5, 500).astype(np.int64)
    npz = os.path.join(tmp, 'bc_testchar.npz')
    np.savez(npz, X=X0, S=S0, Y=Y0,
             meta=np.array(json.dumps({'char': 'testchar'})))

    # npz回退
    kind, base = find_bank('testchar', dirs=[tmp])
    check('npz识别', kind == 'npz', str(kind))
    X, S, Y = load_bank('testchar', dirs=[tmp])
    check('npz加载等值', np.array_equal(X, X0) and np.array_equal(Y, Y0))

    # 转trio(全量)
    npz_to_trio(npz, out_dir=tmp, out_stem='bc_testchar')
    kind, base = find_bank('testchar', dirs=[tmp])
    check('trio优先(npz并存)', kind == 'trio', str(kind))
    X, S, Y = load_bank('testchar', dirs=[tmp])
    check('trio为mmap', isinstance(X, np.memmap) and isinstance(Y, np.memmap))
    check('trio等值', np.array_equal(np.asarray(X), X0)
          and np.array_equal(np.asarray(Y), Y0))
    # 64行抽样(生产消费路径): fancy索引→ndarray拷贝, 值正确
    idx = np.random.default_rng(1).integers(0, len(Y), 64)
    sub = X[idx]
    check('64行抽样', isinstance(sub, np.ndarray) and sub.shape == (64, 40)
          and np.array_equal(sub, X0[idx]))

    # 转换+封顶(回退选项)与meta
    npz2 = os.path.join(tmp, 'bc_capped.npz')
    shutil.copy2(npz, npz2)
    npz_to_trio(npz2, out_dir=tmp, max_rows=100)
    Xc, Sc, Yc = load_bank('capped', dirs=[tmp])
    check('封顶行数', len(np.asarray(Yc)) == 100)
    meta = json.load(open(os.path.join(tmp, 'bc_capped_meta.json'),
                          encoding='utf8'))
    check('封顶meta', meta.get('capped_from') == 500
          and meta.get('capped_to') == 100)
    # 标签占比保持
    for lab in np.unique(Y0):
        a = (Y0 == lab).mean()
        b = (np.asarray(Yc) == lab).mean()
        check('标签%d占比保持' % lab, abs(a - b) < 0.08,
              '%.3f vs %.3f' % (a, b))

    # 无库→None
    check('无库None', load_bank('nonesuch', dirs=[tmp]) is None)

    # ---- P1代际契约(bug_2026-10-14_bc_trio_swap_lock) ----
    # 情形1: 缺meta(换装中断) → 响亮拒绝(不得静默回落)
    import gc
    del X, S, Y          # 释放mmap句柄(Windows文件锁)
    gc.collect()
    os.remove(os.path.join(tmp, 'bc_testchar_meta.json'))
    try:
        load_bank('testchar', dirs=[tmp])
        check('缺meta拒载', False, '未抛异常!')
    except RuntimeError as e:
        check('缺meta拒载', 'meta' in str(e), str(e)[:60])
    # 恢复完整trio(重转)
    npz_to_trio(npz, out_dir=tmp, out_stem='bc_testchar')
    X, S, Y = load_bank('testchar', dirs=[tmp])
    check('重转后可载', len(np.asarray(Y)) == 500)

    # 情形2: 混代际(换Y.npy为另代内容, 行数同) → 哈希拒载
    Y_orig = np.asarray(Y).copy()
    Y_alt = (Y_orig + 1) % 5
    del X, S, Y
    gc.collect()
    np.save(os.path.join(tmp, 'bc_testchar_Y.npy'), Y_alt)
    try:
        load_bank('testchar', dirs=[tmp])
        check('混代际拒载', False, '未抛异常!')
    except RuntimeError as e:
        check('混代际拒载', '哈希' in str(e) or '代际' in str(e),
              str(e)[:60])
    # 恢复后verify=False仍可载(诊断通道)
    np.save(os.path.join(tmp, 'bc_testchar_Y.npy'), Y_orig)
    X2, S2, Y2 = load_bank('testchar', dirs=[tmp], verify=False)
    check('verify=False诊断通道', len(np.asarray(Y2)) == 500)

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
