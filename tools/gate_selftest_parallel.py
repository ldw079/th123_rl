# -*- coding: utf-8 -*-
"""并行变异自检(R159, 用户令"加速sweep"): 多worker并行跑沙箱变异.

原理: 变异循环是 embarrassingly parallel — 每条变异独立沙箱(独立
目录+独立STORE), 无共享状态. 唯一瓶颈:
  ①磁盘(build_sandbox每份~200MB不含mod; N worker×沙箱=磁盘)
  ②CPU(每沙箱门禁=1个python单线程, 18核可跑~12-14并行)
  ③端口: 沙箱contract_check不启游戏(纯静态+测试) — 无端口冲突✓

CPU-H P-A(2026-10-18 用户令"CPU红线要立住"): 重负载必须经 `load_gate`
闸门(单实例锁/preflight/运行时监控/协作停止/轨迹/失败=拒绝启动);
默认 workers **8→2**(18 核 cores//8 派生), 子进程继承 BELOW_NORMAL。
旁路回滚: env `TH123_LOAD_GATE=0`(仅应急, 见 tools/load_gate.py)。

用法: python tools/gate_selftest_parallel.py [N_WORKERS]
缺省 N=2(load_gate.worker_cap 再按 cores//8 收窄并硬上限 4).
"""
from __future__ import annotations

import glob
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
        # CPU-H: 沙箱门禁也走低优先级(子进程已继承, 这里显式兜底)
        env['TH123_LOAD_GATE'] = '0'      # 沙箱内不得再申请闸门(嵌套)
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


def _acquire_gate(req_workers):
    """申请重负载闸门 → (gate|None, ok). ImportError=None,ok 仅本机回退."""
    try:
        from load_gate import acquire
    except ImportError as e:
        print('[load_gate] 模块不可用(%r) — 以默认2 workers继续(无闸门)' % (e,))
        return None, True
    gate = acquire('sweep', workers=req_workers, log=' '.join(sys.argv))
    if gate is None:
        print('[load_gate] 拒绝启动(失败=关闭, 不静默放行) — 退出码2')
        return None, False
    return gate, True


def _make_abort_cb(gate):
    """监控/协作停止时的回调: 杀自身worker池 + 清本任务沙箱 (不碰 fleet)."""
    ctx = {'ex': None}

    def _cb(reason):
        print('[load_gate] 中止回调: %s' % reason, flush=True)
        ex = ctx.get('ex')
        if ex is not None:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            for _pr in list(getattr(ex, '_processes', {}).values()):
                try:
                    _pr.terminate()
                except Exception:
                    pass
        try:
            _root = _sandbox_tmpdir()
            for _d in glob.glob(os.path.join(_root, 'gst_*')):
                shutil.rmtree(_d, ignore_errors=True)
        except Exception:
            pass

    ctx['cb'] = _cb
    if gate is not None:
        gate.set_abort_callback(_cb)
    return ctx


def main():
    req_workers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    gate, gate_ok = _acquire_gate(req_workers)
    if not gate_ok:
        return 2
    n_workers = gate.workers if gate is not None else max(
        1, min(req_workers, 2))
    _tags = [t.strip() for t in
             os.environ.get('SELFTEST_TAGS', '').split(',') if t.strip()]
    todo = []
    for i, (f, old, new, why) in enumerate(MUTATIONS):
        if _tags and not any(t in why for t in _tags):
            continue
        todo.append((i, (f, old, new, why)))

    ctx = _make_abort_cb(gate)

    def _aborted():
        return (gate.poll_abort() if gate is not None else None)

    # P0-4修(从零#5): 基线绿守卫 — 原版无此步, 基线红时所有变异
    # 都"✓红"(rc!=0+FAIL), 结论全部空判. 复用串行版gate_selftest的
    # 基线检查逻辑: 先建一个未变异沙箱跑门禁, 不绿则拒绝继续.
    print('[P0-4] 基线绿守卫检查中...')
    from gate_selftest import _sandbox_tmpdir as _stdir
    _tmp = _stdir()
    _base = tempfile.mkdtemp(prefix='gst_baseline_', dir=_tmp)
    try:
        _sb = os.path.join(_base, 'baseline')
        os.makedirs(_sb)
        build_sandbox(_sb)
        _store = os.path.join(_sb, 'store')
        _env = dict(os.environ)
        _env['TH123_STORE'] = _store
        _env['TH123_MODROOT'] = os.path.join(_sb, 'modroot')
        _env['TH123_BC_DIR'] = os.path.join(_sb, 'bc')
        _env['TH123_ORACLE_MODROOT'] = os.path.join(_sb, 'oraclemod')
        _env['TH123_LOAD_GATE'] = '0'      # 沙箱内不得嵌套申请闸门
        _ml = os.path.join(_sb, 'ModLoaderSettings.json')
        if os.path.exists(_ml):
            _env['TH123_ML'] = _ml
        try:
            _r = subprocess.run(
                [PY, '-X', 'utf8',
                 os.path.join(_sb, 'tools', 'contract_check.py')],
                capture_output=True, text=True, timeout=GATE_TIMEOUT,
                encoding='utf-8', errors='replace', env=_env, cwd=_sb)
            _baseline_rc = _r.returncode
            _baseline_out = (_r.stdout or '') + (_r.stderr or '')
        except subprocess.TimeoutExpired:
            _baseline_rc = 124
            _baseline_out = 'timeout'
        if _aborted():
            print('[load_gate] !! 基线检查期间收到中止: %s' % _aborted())
            shutil.rmtree(_base, ignore_errors=True)
            if gate is not None:
                gate.release(ok=False, note=_aborted())
            return 3
        if _baseline_rc != 0:
            print('[P0-4] !! 基线不绿(exit=%d) — 拒绝继续' % _baseline_rc)
            print('  末行:', _baseline_out.strip().splitlines()[-1][:100]
                  if _baseline_out.strip() else '(无输出)')
            # 2026-10-18 B1: 基线红根因可见化 — 原只打末行, FAIL 项不可见。
            # 落盘完整门禁输出 + 打印 FAIL 行(诊断用; 不改变判定)。
            try:
                _bdir = (r'D:\temp' if os.path.isdir(r'D:\temp')
                         else tempfile.gettempdir())
                _bf = os.path.join(_bdir, 'sweep_baseline_fail_%s.log'
                                   % time.strftime('%Y%m%d_%H%M%S'))
                with open(_bf, 'w', encoding='utf8') as _fh:
                    _fh.write(_baseline_out)
                print('  完整输出:', _bf)
                _fails = [l for l in _baseline_out.splitlines()
                          if '  FAIL' in l]
                for _l in _fails[:10]:
                    print('  FAIL行:', _l.strip()[:200])
            except OSError as _e:
                print('  落盘失败: %r' % (_e,))
            print('  修复门禁后再跑变异自检')
            shutil.rmtree(_base, ignore_errors=True)
            if gate is not None:
                gate.release(ok=False, note='baseline-red')
            return 1
        print('[P0-4] 基线绿 ✓ (exit=0)')
    finally:
        shutil.rmtree(_base, ignore_errors=True)

    print('[并行] %d条变异 × %d workers (C:%.0fGB)'
          % (len(todo), n_workers, _free_gb(ROOT) or -1))

    from concurrent.futures import ProcessPoolExecutor, as_completed
    from concurrent.futures.process import BrokenProcessPool
    t0 = time.time()
    results = []
    aborts = []
    ex = ProcessPoolExecutor(max_workers=n_workers)
    ctx['ex'] = ex
    try:
        futs = {ex.submit(run_one, item): item[0] for item in todo}
        done = 0
        for fut in as_completed(futs):
            try:
                why, ok, detail = fut.result()
            except BrokenProcessPool:
                aborts.append('worker池被中止')
                break
            done += 1
            results.append((why, ok, detail))
            mark = '✓红' if ok else ('○跳过' if ok is None else '✗漏网')
            print('  [%3d/%3d] %s %s (%s)'
                  % (done, len(todo), mark, why[:50], detail))
            _ar = _aborted()
            if _ar:
                aborts.append(_ar)
                break
    except KeyboardInterrupt:
        aborts.append('用户Ctrl-C')
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        ctx['ex'] = None

    el = (time.time() - t0) / 60
    red = sum(1 for _, ok, _ in results if ok is True)
    leaked = [(w, d) for w, ok, d in results if ok is False]
    undet = [(w, d) for w, ok, d in results if ok is None]
    if aborts:
        print('\n==== 并行变异自检: !!中止(%s) — 已完成%d/%d, %d红/%d漏网/%d未判定, '
              '墙钟%.0fmin ===='
              % (aborts[0], len(results), len(todo), red, len(leaked),
                 len(undet), el))
        if gate is not None:
            gate.release(ok=False, note=aborts[0])
        return 3
    print('\n==== 并行变异自检: %d红 / %d漏网 / %d未判定, 墙钟%.0fmin ===='
          % (red, len(leaked), len(undet), el))
    for w, d in leaked:
        print('  ✗ 漏网:', w[:60], '|', d)
    for w, d in undet:
        print('  ○ 未判定:', w[:60], '|', d)
    if gate is not None:
        gate.release(ok=not leaked, note='leaked=%d' % len(leaked))
    return 1 if leaked else 0


if __name__ == '__main__':
    sys.exit(main())
