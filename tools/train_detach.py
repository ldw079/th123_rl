# -*- coding: utf-8 -*-
"""train_detach.py — 脱离 harness Job Object 的训练启动器(task-43/43b).

背景(2026-10-20 19:59 事故): 主臂/对照臂由 DSH harness 会话的 Start-Process 启动，
harness 重启时 Job Object 收口把整棵训练进程树连坐杀掉.

三种脱离方式(按可靠性):
 1) `schtasks`(计划任务): 父进程=svchost/taskeng, 不受 harness Job 影响 — 最可靠(默认)。
 2) `popen` + CREATE_BREAKAWAY_FROM_JOB: 若父 Job 允许 breakaway 则脱离; 本环境实测
    被拒(PermissionError 5) → 自动降级。
 3) `popen` 无 breakaway(DETACHED_PROCESS): 仅脱离控制台, 仍可能被 Job 连坐(最后兜底,响亮告警)。

用法:
  python tools/train_detach.py --mode fleet --actors 3 --tps 360          # 默认自动(优先 schtasks)
  python tools/train_detach.py --via popen ...                            # 强制 Popen
  python tools/train_detach.py --dry --env TH123_MEM_DECISIONS=8
  python tools/train_detach.py --stop
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
DEFAULT_LOG = r'D:\temp\main_detached.log'
DEFAULT_BAT = r'D:\temp\train_detach_launch.bat'
TASK_NAME = 'th123_train_detached'

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
BASE_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def build_env(base, overrides):
    env = dict(base)
    items = overrides.items() if isinstance(overrides, dict) else overrides
    for kv in items:
        if isinstance(kv, str):
            if '=' not in kv:
                raise ValueError('env 覆盖需 KEY=VALUE: %r' % (kv,))
            k, v = kv.split('=', 1)
        else:
            k, v = kv
        env[str(k)] = str(v)
    return env


def build_cmd(mode='fleet', actors=3, tps=360, extra=None):
    cmd = [PY, '-X', 'utf8', '-u',
           os.path.join(ROOT, 'tools', 'train_start.py'), '--mode', str(mode)]
    if str(mode) == 'fleet':
        cmd += ['--actors', str(actors), '--tps', str(tps)]
    if extra:
        cmd += list(extra)
    return cmd


def stop_cmd():
    return [PY, '-X', 'utf8', os.path.join(ROOT, 'tools', 'train_start.py'),
            '--stop']


def write_launcher_bat(bat_path, env, cmd, log_path):
    """写计划任务用 bat: TH123_* env + cd ROOT + 训练命令 >> 日志."""
    def q(s):
        if s == '' or ' ' in s or '"' in s:
            return '"%s"' % s.replace('"', '\"')
        return s
    lines = ['@echo off', 'chcp 65001 >nul',
             'cd /d "%s"' % ROOT]
    for k in sorted(env):
        if str(k).startswith('TH123_'):
            lines.append('set %s=%s' % (k, env[k]))
    lines.append('%s >> "%s" 2>&1' % (' '.join(q(c) for c in cmd), log_path))
    os.makedirs(os.path.dirname(bat_path) or '.', exist_ok=True)
    with open(bat_path, 'w', encoding='utf8', newline='\r\n') as f:
        f.write('\n'.join(lines) + '\n')
    return bat_path


def launch_schtasks(bat_path, task_name=TASK_NAME, dry=False):
    """schtasks 创建+立即运行; 返回 (ok, detail)."""
    st = time.strftime('%H:%M', time.localtime(time.time() + 120))
    create = ['schtasks', '/create', '/tn', task_name, '/tr', bat_path,
              '/sc', 'once', '/st', st, '/f']
    run = ['schtasks', '/run', '/tn', task_name]
    if dry:
        print('[detach][dry] schtasks create:', ' '.join(create))
        print('[detach][dry] schtasks run:', ' '.join(run))
        return True, 'dry'
    r1 = subprocess.run(create, capture_output=True, text=True)
    if r1.returncode != 0:
        return False, 'create rc=%d %s' % (r1.returncode,
                                           (r1.stdout + r1.stderr)[-300:])
    r2 = subprocess.run(run, capture_output=True, text=True)
    if r2.returncode != 0:
        return False, 'run rc=%d %s' % (r2.returncode,
                                        (r2.stdout + r2.stderr)[-300:])
    return True, 'task=%s st=%s' % (task_name, st)


def launch_popen(cmd, cwd, env, log_path, dry=False):
    line = ' '.join('"%s"' % c if ' ' in c else c for c in cmd)
    if dry:
        print('[detach][dry] cwd=%s' % cwd)
        print('[detach][dry] env=%s' % {k: env[k] for k in sorted(env)
                                       if k.startswith('TH123_')})
        print('[detach][dry] log=%s' % log_path)
        print('[detach][dry] cmd=%s' % line)
        return {'pid': None, 'mode': 'dry', 'line': line}
    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)
    for use_break in (True, False):
        flags = BASE_FLAGS | (CREATE_BREAKAWAY_FROM_JOB if use_break else 0)
        log = None
        try:
            log = open(log_path, 'ab', buffering=0)
            p = subprocess.Popen(
                cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                creationflags=flags)
        except OSError as e:
            print('[detach] breakaway=%s 启动失败: %r' % (use_break, e))
            if log is not None:
                try:
                    log.close()
                except Exception:
                    pass
            continue
        return {'pid': p.pid,
                'mode': 'popen_breakaway' if use_break else 'popen_fallback',
                'line': line}
    return {'pid': None, 'mode': 'fail', 'line': line}


def launch(cmd, cwd, env, log_path, dry=False, via='auto'):
    """统一入口; via ∈ auto|popen|schtasks."""
    if dry:
        line = ' '.join('"%s"' % c if ' ' in c else c for c in cmd)
        print('[detach][dry] cwd=%s' % cwd)
        print('[detach][dry] env=%s' % {k: env[k] for k in sorted(env)
                                       if k.startswith('TH123_')})
        print('[detach][dry] log=%s' % log_path)
        print('[detach][dry] flags=detached|new_group|breakaway|no_window')
        print('[detach][dry] cmd=%s' % line)
        if via in ('auto', 'schtasks'):
            print('[detach][dry] schtasks create/run (batch=%s)'
                  % DEFAULT_BAT)
        return {'pid': None, 'mode': 'dry', 'line': line}
    if via in ('auto', 'schtasks'):
        bat = write_launcher_bat(DEFAULT_BAT, env, cmd, log_path)
        ok, detail = launch_schtasks(bat)
        if ok:
            print('[detach] schtasks 启动成功:', detail)
            return {'pid': -1, 'mode': 'schtasks', 'line': ' '.join(cmd),
                    'task': TASK_NAME}
        print('[detach] schtasks 失败(%s) — 回退 Popen' % detail)
        if via == 'schtasks':
            return {'pid': None, 'mode': 'fail', 'line': ' '.join(cmd)}
    res = launch_popen(cmd, cwd, env, log_path)
    if res['mode'] == 'popen_fallback':
        print('[detach] WARN: breakaway 被 Job 限制 — 已回退 detached Popen'
              '(仍可能被 harness 重启连坐; 建议 schtasks/计划任务)')
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='fleet')
    ap.add_argument('--actors', type=int, default=3)
    ap.add_argument('--tps', type=int, default=360)
    ap.add_argument('--env', action='append', default=[])
    ap.add_argument('--log', default=DEFAULT_LOG)
    ap.add_argument('--via', choices=['auto', 'popen', 'schtasks'],
                    default='auto')
    ap.add_argument('--stop', action='store_true')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    if a.stop:
        return subprocess.run(stop_cmd()).returncode
    env = build_env(os.environ, a.env)
    for k in ('TH123_BATCH_MIN_GAMES', 'TH123_BATCH_MIN_DECISIONS',
              'TH123_BCW_MIN', 'TH123_BCW_START'):
        env.pop(k, None)
    cmd = build_cmd(a.mode, a.actors, a.tps)
    res = launch(cmd, ROOT, env, a.log, dry=a.dry, via=a.via)
    if a.dry:
        return 0
    if res['pid'] is None:
        print('[detach] FAIL — 未能启动训练')
        return 1
    print('[detach] mode=%s pid=%s log=%s'
          % (res['mode'], res['pid'], a.log))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
