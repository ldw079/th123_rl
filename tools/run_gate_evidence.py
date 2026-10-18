# -*- coding: utf-8 -*-
"""门禁证据产物: 一次写入、不可复写(task-18, 审计#7 要求).

背景: 旧脚本 `D:\\temp\\run_gate_r200.py` / `run_gate_r201.py` 用固定文件名
`gate_r200.txt` — 重跑会**覆盖**已入提交信息的证据(本轮 R201 的 675 证据
即被 R202 覆盖)。规范: 产物名 `gate_r<rev>_<commit7>_<ts>.txt/.exit`,
以 `O_EXCL` 独占创建 —— 同名已存在则**响亮拒绝**(不覆盖、不改写)。

用法:
  python tools/run_gate_evidence.py --rev 203 [--out D:\\temp] [--ts YYYYmmdd_HHMMSS]
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = r'D:\temp' if os.path.isdir(r'D:\temp') else os.getcwd()


def short_commit(cwd=None):
    """当前 HEAD 7 位短哈希(证据名的一部分; 失败返回 'unknown')."""
    try:
        r = subprocess.run(['git', 'rev-parse', '--short=7', 'HEAD'],
                           cwd=cwd or ROOT, capture_output=True, text=True,
                           timeout=20)
        h = (r.stdout or '').strip()
        return h if r.returncode == 0 and h else 'unknown'
    except Exception:
        return 'unknown'


def evidence_stem(rev, commit, ts):
    """证据文件名主干: gate_r<rev>_<commit7>_<ts> (无扩展名)。"""
    return 'gate_r%s_%s_%s' % (str(rev), str(commit)[:7], str(ts))


def evidence_paths(out_dir, rev, commit, ts):
    """→ (txt_path, exit_path)。命名含 rev/commit/ts(可审计、不冲突)。"""
    stem = evidence_stem(rev, commit, ts)
    return (os.path.join(out_dir, stem + '.txt'),
            os.path.join(out_dir, stem + '.exit'))


def exclusive_create(path):
    """O_EXCL 独占创建空文件; 已存在 → FileExistsError(不覆盖)。"""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    return fd


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--rev', required=True, help='修订号(如 203)')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--ts', default=None,
                    help='时间戳 YYYYmmdd_HHMMSS(默认当前时刻)')
    ap.add_argument('--commit', default=None, help='7位commit(默认 HEAD)')
    args = ap.parse_args(argv)
    ts = args.ts or time.strftime('%Y%m%d_%H%M%S')
    commit = args.commit or short_commit()
    txt, exi = evidence_paths(args.out, args.rev, commit, ts)
    os.makedirs(args.out, exist_ok=True)
    # 写一次: 两个文件都先独占创建(任一已存在=冲突 → 拒绝, 不覆盖)
    fd_txt = exclusive_create(txt)
    try:
        fd_exi = exclusive_create(exi)
    except FileExistsError:
        os.close(fd_txt)
        print('[gate-evidence] !! 拒绝: 证据文件已存在(不复写): %s' % exi)
        return 2
    os.close(fd_txt)
    os.close(fd_exi)
    print('[gate-evidence] 产物: %s (+.exit) commit=%s ts=%s'
          % (txt, commit, ts))
    with io.open(txt, 'wb') as f:
        r = subprocess.run(
            [sys.executable, '-X', 'utf8',
             os.path.join(ROOT, 'tools', 'contract_check.py')],
            cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
            creationflags=0x4000)
    with io.open(exi, 'w', encoding='ascii') as g:
        g.write(str(r.returncode))
    print('[gate-evidence] exit=%d' % r.returncode)
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
