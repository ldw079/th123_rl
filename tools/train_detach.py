# -*- coding: utf-8 -*-
"""train_detach.py — 脱离 harness Job Object 的训练启动器(task-43).

背景(2026-10-20 19:59 事故): 主臂/对照臂由 DSH harness 会话的 Start-Process 启动，
harness 重启时 Job Object 收口把整棵训练进程树连坐杀掉 → 需要 DETACHED_PROCESS +
CREATE_BREAKAWAY_FROM_JOB 启动，父进程为系统且不受 harness 生命周期影响。

用法:
  python tools/train_detach.py --mode fleet --actors 3 --tps 360
  python tools/train_detach.py --dry --env TH123_MEM_DECISIONS=8   # 只打印不启动
  python tools/train_detach.py --stop                              # 透传 train_start --stop

实现: Win32 CreateProcessW + DETACHED_PROCESS(0x8) | CREATE_NEW_PROCESS_GROUP(0x200)
| CREATE_BREAKAWAY_FROM_JOB(0x01000000); 若 breakaway 被 Job 限制(错误 5/1314)则回退
不带 breakaway 并打印响亮告警(至少 DETACHED_PROCESS 仍生效).
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
DEFAULT_LOG = r'D:\temp\main_detached.log'

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def build_env(base, overrides):
    """合并环境: base 复制后叠加 overrides(K=V 字符串或 dict)。"""
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
    cmd = [PY, '-X', 'utf8', '-u', os.path.join(ROOT, 'tools', 'train_start.py'),
           '--mode', str(mode)]
    if str(mode) == 'fleet':
        cmd += ['--actors', str(actors), '--tps', str(tps)]
    if extra:
        cmd += list(extra)
    return cmd


def _startupinfo():
    si = ctypes.create_string_buffer(104)   # STARTUPINFOW 尺寸(含 padding)足够
    return si


def launch(cmd, cwd, env, log_path, dry=False):
    """CreateProcessW 启动; 返回 (pid, used_breakaway) 或 (None, False)."""
    line = ' '.join('"%s"' % c if ' ' in c else c for c in cmd)
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    if dry:
        print('[detach][dry] cwd=%s' % cwd)
        print('[detach][dry] env=%s' % {k: env[k] for k in sorted(env)
                                       if k.startswith('TH123_')})
        print('[detach][dry] log=%s' % log_path)
        print('[detach][dry] flags=detached|new_group|breakaway|no_window')
        print('[detach][dry] cmd=%s' % line)
        return None, True, line
    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)
    # 重定向 stdout/stderr 到日志(子进程继承)
    log = open(log_path, 'ab', buffering=0)
    try:
        for use_break in (True, False):
            fl = flags | (CREATE_BREAKAWAY_FROM_JOB if use_break else 0)
            try:
                rc = _create_process(line, cwd, env, fl, log)
            except OSError as e:
                print('[detach] breakaway=%s 失败: %r' % (use_break, e))
                continue
            if rc:
                return rc, use_break, line
        return None, False, line
    finally:
        log.close()


def _create_process(line, cwd, env, flags, log):
    """ctypes CreateProcessW; 返回 PID 或 None."""
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi32 = ctypes.WinDLL('advapi32')

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
            ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
            ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
            ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD),
            ('dwXCountChars', wintypes.DWORD),
            ('dwYCountChars', wintypes.DWORD),
            ('dwFillAttribute', wintypes.DWORD),
            ('dwFlags', wintypes.DWORD), ('wShowWindow', wintypes.WORD),
            ('cbReserved2', wintypes.WORD),
            ('lpReserved2', ctypes.POINTER(ctypes.c_byte)),
            ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE),
            ('hStdError', wintypes.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [('hProcess', wintypes.HANDLE),
                    ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD),
                    ('dwThreadId', wintypes.DWORD)]

    # 继承日志句柄到子进程 stdout/stderr
    import msvcrt
    log_fd = log.fileno()
    log_os = msvcrt.get_osfhandle(log_fd)
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
    si.hStdInput = None
    si.hStdOutput = log_os
    si.hStdError = log_os
    pi = PROCESS_INFORMATION()
    env_block = ctypes.create_unicode_buffer(
        '\0'.join('%s=%s' % (k, v) for k, v in env.items()) + '\0\0')
    ok = kernel32.CreateProcessW(
        None, ctypes.create_unicode_buffer(line), None, None, True, flags,
        env_block, cwd, ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        err = ctypes.get_last_error() or 1
        raise OSError(0, 'CreateProcessW failed', err)
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(pi.hProcess)
    return int(pi.dwProcessId)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='fleet')
    ap.add_argument('--actors', type=int, default=3)
    ap.add_argument('--tps', type=int, default=360)
    ap.add_argument('--env', action='append', default=[])
    ap.add_argument('--log', default=DEFAULT_LOG)
    ap.add_argument('--stop', action='store_true')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    if a.stop:
        rc = subprocess = __import__('subprocess').run(
            [PY, '-X', 'utf8', os.path.join(ROOT, 'tools', 'train_start.py'),
             '--stop'])
        return rc.returncode
    env = build_env(os.environ, a.env)
    # 显式去掉批放大/BCW 环境(避免旧 env 残留; 按窗需要再 --env 覆盖)
    for k in ('TH123_BATCH_MIN_GAMES', 'TH123_BATCH_MIN_DECISIONS',
              'TH123_BCW_MIN', 'TH123_BCW_START'):
        env.pop(k, None)
    cmd = build_cmd(a.mode, a.actors, a.tps)
    pid, used_break, line = launch(cmd, ROOT, env, a.log, dry=a.dry)
    if a.dry:
        return 0
    if pid is None:
        print('[detach] FAIL — 未能启动训练 (见上错误)')
        return 1
    print('[detach] started pid=%d breakaway=%s log=%s'
          % (pid, used_break, a.log))
    if not used_break:
        print('[detach] WARN: breakaway 被 Job 限制, 已回退(仍 detached; '
              '若 harness 重启可能连坐 — 建议由计划任务启动)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
