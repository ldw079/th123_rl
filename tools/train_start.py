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


def _cleanup_ps_cmd(exclude_pid):
    """构造残留清理命令 — 排除exclude_pid(调用者自身).

    教训×3(2026-10-11实弹复现): 特征串含'exploiter'会匹配**自身命令行**
    的 --exploiter 参数 → taskkill /T /F 连树自杀(启动即死, 日志止于
    "[前置] 残留进程清理"行, stderr空, 什么都没启动). 修: Where-Object
    加 ProcessId -ne 自身PID(清理powershell本身是powershell.exe,
    不吃Name='python.exe'过滤, 无需另排除).
    审计#3 P1-6: 游戏清理原taskkill /IM th123.exe /F按映像名无差别杀
    — 会误杀用户游玩中的原版整合包与rl_game离线重放实例。改按
    ExecutablePath含th123_train精确匹配(训练族游戏专用目录)。
    """
    return ['powershell', '-NoProfile', '-Command',
            "$me=%d; Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
            "| Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -match "
            "'fleet_supervisor|run_parallel|learner_hub|actor_worker"
            "|exploiter'} "
            "| ForEach-Object { taskkill /PID $_.ProcessId /T /F }; "
            "Start-Sleep 2; "
            "Get-CimInstance Win32_Process -Filter \"Name='th123.exe'\" "
            "| Where-Object { $_.ExecutablePath -like '*th123_train*' } "
            "| ForEach-Object { taskkill /PID $_.ProcessId /T /F }"
            % int(exclude_pid)]


def pre_flight():
    print('[前置] 残留进程清理(按命令行精确匹配 — 不全杀python)...',
          flush=True)
    # 教训×2: 原版Get-Process python全杀 → (a)启动器自杀 (b)会话宿主
    # 被连带(bash工具链里有python). 改为只杀训练族进程(命令行含特征串)
    subprocess.run(_cleanup_ps_cmd(os.getpid()), capture_output=True)
    free = ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        'D:\\', None, None, ctypes.byref(free))
    gb = free.value / 2 ** 30
    print('[前置] D盘剩余 %.1fGB %s' % (gb, 'OK' if gb > 2 else '!!低'))
    # D3'(R65): league对手生态种子幂等补种(缺的补, 已有跳过; 失败不阻断
    # — actor侧非严格build_opp_cycle+轮换安全跳过双兜底)
    try:
        from tools.seed_league_pool import seed_league_pool
        _seeded, _skip, _rej = seed_league_pool(verbose=False)
        print('[前置] league种子: 补%d 已有%d 拒%d' % (
            len(_seeded), len(_skip), len(_rej)))
    except Exception as e:
        print('[前置] league种子异常(%s) — 继续(双兜底)' % e)
    r = subprocess.run([PY, '-X', 'utf8',
                        os.path.join(ROOT, 'tests', 'test_fleet_protocol.py')],
                       capture_output=True, cwd=ROOT)
    ok = r.returncode == 0
    print('[前置] fleet协议测试 %s' % ('21+ PASS' if ok else '!!FAIL — 先修'))
    # P0(从零#4, bug_bc_width_asymmetry): BC库宽度硬门禁 — 代际迁移期
    # "BC未重建+fleet已点火"=actor连环崩→重启耗尽→静默减员(16:12事故
    # 根因链)。部署序列(迁移→重建→换装→点火)从此是硬顺序。
    try:
        import numpy as _np
        from feat_builder import FeatureBuilder as _FB
        from train_tm import CHAR_LIBS as _CL
        _store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
        _bc_ok = True
        for _ch in ('reimu', 'marisa', 'suika'):
            _sp = os.path.join(_store, 'bc_%s_S.npy' % _ch)
            _xp = os.path.join(_store, 'bc_%s_X.npy' % _ch)
            if not (os.path.exists(_sp) and os.path.exists(_xp)):
                print('[前置] !!FAIL BC库缺失 %s — 先重建/换装再点火' % _ch)
                _bc_ok = False
                continue
            _w = _np.load(_sp, mmap_mode='r').shape[1]
            _exp = 5 * len(_CL[_ch]['macros']) + _FB.CORE_DIMS
            if _w != _exp:
                print('[前置] !!FAIL BC库宽度 %s S=%d≠派生%d — '
                      '代际未换装, 拒点火(防连环崩减员)' % (_ch, _w, _exp))
                _bc_ok = False
        if _bc_ok:
            print('[前置] BC库宽度×3 OK(=5N+CORE_DIMS)')
    except Exception as _e:
        print('[前置] !!FAIL BC宽度预检异常: %r — 拒点火' % _e)
        _bc_ok = False
    return ok and gb > 2 and _bc_ok


def start(mode, actors, exploiter, tps=480, hours=None,
          exploit_target=None):
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
         '--actors', str(actors), '--tps', str(tps)]
        + (['--hours', hours] if hours else []),
        cwd=ROOT)
    if exploiter:
        print('[启动] 剥削者 %s%s (30s后错峰)...' % (
            exploiter,
            ' →定向%s' % exploit_target if exploit_target else '(镜像)'))
        time.sleep(30)
        _cmd = [PY, '-X', 'utf8', '-u', 'exploiter.py',
                '--char', exploiter, '--fleet']
        if exploit_target:
            _cmd += ['--target', exploit_target]
        subprocess.Popen(_cmd, cwd=ROOT)
    print('\n[监控] python tools/audit_all.py  (手动审计)')
    print('[停机] python tools/train_start.py --stop')
    print('[监督日志] D:\\temp\\th123_models\\fleet_supervision.log')
    return 0


def stop_all():
    # 审计#3 P1-6: --stop原复用pre_flight — 附带跑协议测试+league种子
    # (副作用未声明)。停机只需要清理本身。
    print('[停机] 树杀全部训练进程(游戏仅限th123_train族)...')
    subprocess.run(_cleanup_ps_cmd(os.getpid()), capture_output=True)
    print('[停机] 完成')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='fleet', choices=['fleet', 'single'])
    ap.add_argument('--actors', type=int, default=4)
    ap.add_argument('--hours', default=None,
                    help='运营窗口(C1-2, 如 9:00-23:00)')
    ap.add_argument('--tps', type=int, default=480,
                    help='actor tps(R14 CPU红线: 建议360)')
    ap.add_argument('--exploit-target', default=None,
                    help='D1-2定向对手(如suika; 缺省镜像)')
    ap.add_argument('--exploiter', default=None,
                    help='剥削者角色(如 reimu) — 与fleet同池弱侧专项')
    ap.add_argument('--stop', action='store_true')
    a = ap.parse_args()
    if a.stop:
        stop_all()
    else:
        sys.exit(start(a.mode, a.actors, a.exploiter, a.tps, a.hours,
                 a.exploit_target))


if __name__ == '__main__':
    main()
