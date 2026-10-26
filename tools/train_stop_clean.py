# -*- coding: utf-8 -*-
"""干净停机 helper（用户关机前/维护用）: 停 watcher→control→main，写标记+停机账.

用户裁定 2026-10-26 10:06: **不自动恢复**；本 helper 供主动关机前优雅停训。
不做 Windows 关机事件自动响应（高风险），不安装自启任务。

用法:
  python tools/train_stop_clean.py [--dry-run] [--keep-control] [--timeout 90]
输出: 标记 `STORE/train_stopped_clean` + 日志 `D:\temp\train_stop_clean.log`
"""
import argparse
import base64
import json
import os
import subprocess
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
STORE = r'D:\temp\th123_models'
MARK = os.path.join(STORE, 'train_stopped_clean')
LOG = r'D:\temp\train_stop_clean.log'
LOG_ALIAS = r'D:\temp\clean_shutdown.log'


def _ps_json(script):
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', enc],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=120)
    return (r.stdout or '').strip()


def _pids(script):
    return [int(x) for x in _ps_json(script).split() if x.strip().isdigit()]


TEST_DIR = os.environ.get('TH123_STOP_TEST_DIR')
TEST_MARKER = os.environ.get('TH123_STOP_TEST_MARKER')
STORE = TEST_DIR or STORE
MARK = os.path.join(STORE, 'train_stopped_clean')


def _mk(marker):
    if not marker:
        return ''
    safe = re.sub(r"[^A-Za-z0-9_]", '', marker)
    return " -and $_.CommandLine -match '%s'" % safe


def _cmdline(pid):
    out = _ps_json("(Get-CimInstance Win32_Process -Filter "
                   "'ProcessId=%d').CommandLine" % int(pid))
    return out or ''


def _verify_target(pid, marker):
    """杀前校验: test 模式必须含 marker; live 模式必须是 main/control/watcher/game 已知族."""
    cl = _cmdline(pid)
    if marker:
        return marker in cl
    return any(k in cl for k in ('learner_hub', 'actor_worker',
                                 'fleet_supervisor', 'th123_rl_control',
                                 'fleet_health.py --loop', 'th123.exe'))


def main_pids(marker=None):
    return _pids("Get-CimInstance Win32_Process | ? {$_.Name -eq 'python.exe' "
                 "-and $_.CommandLine -match 'learner_hub|actor_worker|"
                 "fleet_supervisor' -and $_.CommandLine -notmatch "
                 "'th123_rl_control'" + _mk(marker) + "} | % {$_.ProcessId}")


def control_pids(marker=None):
    return _pids("Get-CimInstance Win32_Process | ? {$_.Name -eq 'python.exe' "
                 "-and $_.CommandLine -match 'th123_rl_control'" +
                 _mk(marker) + "} | % {$_.ProcessId}")


def watcher_pids(marker=None):
    return _pids("Get-CimInstance Win32_Process | ? {$_.Name -eq 'python.exe' "
                 "-and $_.CommandLine -match 'fleet_health.py --loop'" +
                 _mk(marker) + "} | % {$_.ProcessId}")


def game_pids(marker=None):
    return _pids("Get-CimInstance Win32_Process | ? {$_.Name -eq "
                 "'th123.exe'" + _mk(marker) + "} | % {$_.ProcessId}")


def log(msg):
    try:
        line = '[%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg)
        with open(LOG, 'a', encoding='utf8') as f:
            f.write(line)
        with open(LOG_ALIAS, 'a', encoding='utf8') as f:
            f.write(line)
    except OSError:
        pass


def kill_pid(pid, tag=''):
    try:
        r = subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=30)
        ok = getattr(r, 'returncode', 1) == 0
        log('kill %s pid=%d ok=%s' % (tag, pid, ok))
        return ok
    except Exception as e:
        log('kill %s pid=%d exception=%r' % (tag, pid, e))
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--keep-control', action='store_true')
    ap.add_argument('--timeout', type=int, default=90)
    ap.add_argument('--reason', default='manual clean stop')
    ap.add_argument('--live', action='store_true',
                    help='真停（默认拒绝：无 --live 仅打印/拒绝）')
    a = ap.parse_args()
    if TEST_DIR and not TEST_MARKER:
        print('[stop_clean] TEST_DIR set but TEST_MARKER missing — abort')
        return 2
    if not TEST_DIR and not a.live:
        print('[stop_clean] real stop requires --live (safety) — abort')
        return 3
    m = TEST_MARKER
    snap = {'ts': time.time(), 'main': main_pids(m),
            'control': control_pids(m), 'watcher': watcher_pids(m),
            'games': game_pids(m), 'reason': a.reason}
    log('start dry=%s %s' % (a.dry_run, json.dumps(snap)))
    print('[stop_clean]', json.dumps(snap, ensure_ascii=False))
    if a.dry_run:
        print('[stop_clean] dry-run — no action')
        return 0
    # 0) maintenance lock (test mode: temp path)
    try:
        import fleet_lock
        if TEST_DIR:
            fleet_lock.LOCK = os.path.join(TEST_DIR,
                                           'fleet_maintenance.lock')
        _lk = fleet_lock.acquire('train_stop_clean', a.reason, ttl=1200)
        print('[stop_clean] lock', _lk[1])
        if not _lk[0] and not TEST_DIR:
            print('[stop_clean] live stop blocked by maintenance lock — abort')
            return 4
    except Exception as e:
        print('[stop_clean] lock exception', repr(e))
        if not TEST_DIR:
            return 5
    # 1) watcher first (防自动恢复抢跑)
    for pid in snap['watcher']:
        if _verify_target(pid, m):
            kill_pid(pid, 'watcher')
    # 2) control arm
    if not a.keep_control:
        for pid in snap['control']:
            if _verify_target(pid, m):
                kill_pid(pid, 'control')
    # 3) main graceful (test mode: no real train_start)
    if not TEST_DIR:
        subprocess.run([sys.executable, '-X', 'utf8',
                        os.path.join(ROOT, 'tools', 'train_start.py'),
                        '--stop'], cwd=ROOT, capture_output=True,
                       timeout=120)
    t0 = time.time()
    while time.time() - t0 < a.timeout and main_pids(m):
        time.sleep(3)
    left = main_pids(m)
    for pid in left:
        if _verify_target(pid, m):
            kill_pid(pid, 'main_left')
    # 4) leftover games (main only; control games untouched if keep_control)
    left_games = game_pids(m)
    if not a.keep_control:
        for pid in left_games:
            if _verify_target(pid, m):
                kill_pid(pid, 'game')
        left_games = game_pids(m)
    left_main = main_pids(m)
    entry = {'ts': time.time(), 'reason': a.reason, 'before': snap,
             'after_main': left_main, 'after_games': left_games,
             'control_kept': bool(a.keep_control)}
    try:
        os.makedirs(STORE, exist_ok=True)
        with open(MARK, 'w', encoding='utf8') as f:
            json.dump(entry, f, ensure_ascii=False)
    except OSError:
        pass
    try:
        import fleet_lock
        fleet_lock.release(owner='train_stop_clean', force=True)
    except Exception:
        pass
    log('done left_main=%s left_games=%s' % (left_main, left_games))
    print('[stop_clean] left main=%s games=%s' % (left_main, left_games))
    return 0 if (not left_main and (a.keep_control or not left_games)) else 1


if __name__ == '__main__':
    sys.exit(main())
