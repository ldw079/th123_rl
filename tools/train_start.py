# -*- coding: utf-8 -*-
"""训练启动配置集合(用户2026-10-07指令: 启动配置归本脚本)。

一条命令带全部配置启动训练(替代手敲多条长命令):

  python tools/train_start.py                      # 默认: fleet 4 actor
  python tools/train_start.py --mode fleet --actors 3 --exploiter reimu
  python tools/train_start.py --mode single        # 单实例(run_parallel)
  python tools/train_start.py --stop               # 树杀全部训练

配置要点(2026-10-07定稿):
  - fleet 4 actor = 容量标定上限(6actor实测CPU 100%饱和learner饿死)
  - 剥削者与fleet同池(--fleet), 弱侧角色优先(reimu: 矩阵0%+双流派0%)
  - 启动前自动: 残留清理 → fleet协议测试 → 磁盘检查
  - 全部修复(维度守卫/C三层卡组池/R62胜负挂钩/distill重试)随进程生效
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

PY = sys.executable


def pre_flight():
    print('[前置] 残留进程清理(按命令行精确匹配 — 不全杀python)...',
          flush=True)
    # 教训×2: 原版Get-Process python全杀 → (a)启动器自杀 (b)会话宿主
    # 被连带(bash工具链里有python). 改为只杀训练族进程(命令行含特征串)
    subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
         "| Where-Object {$_.CommandLine -match "
         "'fleet_supervisor|run_parallel|learner_hub|actor_worker"
         "|exploiter'} "
         "| ForEach-Object { taskkill /PID $_.ProcessId /T /F }; "
         "Start-Sleep 2; taskkill /IM th123.exe /F 2>$null"],
        capture_output=True)
    free = ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        'D:\\', None, None, ctypes.byref(free))
    gb = free.value / 2 ** 30
    print('[前置] D盘剩余 %.1fGB %s' % (gb, 'OK' if gb > 2 else '!!低'))
    r = subprocess.run([PY, '-X', 'utf8',
                        os.path.join(ROOT, 'test_fleet_protocol.py')],
                       capture_output=True, cwd=ROOT)
    ok = r.returncode == 0
    print('[前置] fleet协议测试 %s' % ('21+ PASS' if ok else '!!FAIL — 先修'))
    return ok and gb > 2


def start(mode, actors, exploiter):
    if not pre_flight():
        return 1
    if mode == 'single':
        print('[启动] 单实例 run_parallel 5000')
        subprocess.Popen(
            [PY, '-X', 'utf8', '-u', 'run_parallel.py', '5000'],
            cwd=ROOT)
        return 0
    print('[启动] fleet %d actor...' % actors)
    p = subprocess.Popen(
        [PY, '-X', 'utf8', '-u', 'fleet_supervisor.py',
         '--actors', str(actors)],
        cwd=ROOT)
    if exploiter:
        print('[启动] 剥削者 %s (30s后错峰)...' % exploiter)
        time.sleep(30)
        subprocess.Popen(
            [PY, '-X', 'utf8', '-u', 'exploiter.py',
             '--char', exploiter, '--fleet'],
            cwd=ROOT)
    print('\n[监控] python tools/audit_all.py  (手动审计)')
    print('[停机] python tools/train_start.py --stop')
    print('[监督日志] D:\\temp\\th123_models\\fleet_supervision.log')
    return 0


def stop_all():
    print('[停机] 树杀全部训练进程...')
    pre_flight()
    print('[停机] 完成')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='fleet', choices=['fleet', 'single'])
    ap.add_argument('--actors', type=int, default=4)
    ap.add_argument('--exploiter', default=None,
                    help='剥削者角色(如 reimu) — 与fleet同池弱侧专项')
    ap.add_argument('--stop', action='store_true')
    a = ap.parse_args()
    if a.stop:
        stop_all()
    else:
        sys.exit(start(a.mode, a.actors, a.exploiter))


if __name__ == '__main__':
    main()
