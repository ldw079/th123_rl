# -*- coding: utf-8 -*-
"""并行变异自检(R159, 用户令"加速sweep"): 多worker并行跑沙箱变异.

原理: 变异循环是 embarrassingly parallel — 每条变异独立沙箱(独立
目录+独立STORE), 无共享状态. 唯一瓶颈:
  ①磁盘(build_sandbox每份~200MB不含mod; N worker×沙箱=磁盘)
  ②CPU(每沙箱门禁=1个python单线程, 18核可跑~12-14并行)
  ③端口: 沙箱contract_check不启游戏(纯静态+测试) — 无端口冲突✓

用法: python tools/gate_selftest_parallel.py [N_WORKERS]
缺省N=8(保守: 主fleet 12 py+4 game占~8核, 余10核; 8 worker×沙箱
磁盘~1.6GB×8=13GB, D:65GB余量充足).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

PY = sys.executable
GATE_TIMEOUT = int(os.environ.get('SELFTEST_GATE_TIMEOUT', '2700'))

# 复用主工具的MUTATIONS + build_sandbox
from gate_selftest import (MUTATIONS, build_sandbox, _free_gb,
                           _sandbox_tmpdir)


def run_one(args):
    """单条变异: 建沙箱→变异→跑门禁→清理 → (why, ok, detail)."""
    idx, (f, old, new, why) = args
    t0 = time.time()
    base = None
    try:
        _tmp = _sandbox_tmpdir()
        base = tempfile.mkdtemp(prefix="gst_par_", dir=_tmp)
        sb = os.path.join(base, "mut")
        os.makedirs(sb)
        build_sandbox(sb)
        store = os.path.join(sb, "store")
        target = os.path.join(sb, f)
        if not os.path.exists(target):
            return why, None, '沙箱无此文件(跳过)'
        txt = open(target, encoding='utf-8').read()
        if txt.count(old) < 1:
            return why, False, '变异定义失效(模式未命中)'
        open(target, 'w', encoding='utf-8').write(txt.replace(old, new))

        env = dict(os.environ)
        env['TH123_STORE'] = store
        env['TH123_MODROOT'] = os.path.join(sb, 'modroot')
        env['TH123_BC_DIR'] = os.path.join(sb, 'bc')
        env['TH123_ORACLE_MODROOT'] = os.path.join(sb, 'oraclemod')
        _ml = os.path.join(sb, 'ModLoaderSettings.json')
        if os.path.exists(_ml):
            env['TH123_ML'] = _ml
        try:
            r = subprocess.run(
                [PY, '-X', 'utf8', os.path.join(sb, 'tools',
                                                 'contract_check.py')],
                capture_output=True, text=True, timeout=GATE_TIMEOUT,
                encoding='utf-8', errors='replace', env=env,
                cwd=sb)
            rc, out = r.returncode, (r.stdout or '') + (r.stderr or '')
        except subprocess.TimeoutExpired:
            return why, None, '超时未判定'
        ok = rc != 0 and ('  FAIL' in out or 'FAIL项' in out)
        return why, ok, 'exit=%d %.0fs' % (rc, time.time() - t0)
    except Exception as e:
        return why, None, '异常: %r' % e
    finally:
        if base:
            shutil.rmtree(base, ignore_errors=True)


def main():
    n_workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    _tags = [t.strip() for t in
             os.environ.get('SELFTEST_TAGS', '').split(',') if t.strip()]
    todo = []
    for i, (f, old, new, why) in enumerate(MUTATIONS):
        if _tags and not any(t in why for t in _tags):
            continue
        todo.append((i, (f, old, new, why)))
    print('[并行] %d条变异 × %d workers (D:%.0fGB)'
          % (len(todo), n_workers, _free_gb(ROOT) or -1))

    from concurrent.futures import ProcessPoolExecutor, as_completed
    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futs = {ex.submit(run_one, item): item[0] for item in todo}
        done = 0
        for fut in as_completed(futs):
            why, ok, detail = fut.result()
            done += 1
            results.append((why, ok, detail))
            mark = '✓红' if ok else ('○跳过' if ok is None else '✗漏网')
            print('  [%3d/%3d] %s %s (%s)'
                  % (done, len(todo), mark, why[:50], detail))

    el = (time.time() - t0) / 60
    red = sum(1 for _, ok, _ in results if ok is True)
    leaked = [(w, d) for w, ok, d in results if ok is False]
    undet = [(w, d) for w, ok, d in results if ok is None]
    print('\n==== 并行变异自检: %d红 / %d漏网 / %d未判定, 墙钟%.0fmin ===='
          % (red, len(leaked), len(undet), el))
    for w, d in leaked:
        print('  ✗ 漏网:', w[:60], '|', d)
    for w, d in undet:
        print('  ○ 未判定:', w[:60], '|', d)
    return 1 if leaked else 0


if __name__ == '__main__':
    sys.exit(main())
