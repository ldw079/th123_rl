# -*- coding: utf-8 -*-
"""R15 行为测试: 干净停机 helper (真实 dummy: main/control/watcher 按 PID 停止)."""
import os
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import train_stop_clean as T  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _spawn(role, marker):
    return subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(180)',
         'stopclean_marker_' + marker, role])


def test_stop_clean_real():
    d = tempfile.mkdtemp(prefix='stop_clean_')
    marker = uuid.uuid4().hex[:8]
    procs = [
        _spawn('main learner_hub', marker),
        _spawn('main actor_worker', marker),
        _spawn('fleet_supervisor', marker),
        _spawn('fleet_health.py --loop', marker),
        _spawn('th123_rl_control learner_hub', marker),
    ]
    time.sleep(2.5)
    try:
        env = dict(os.environ)
        env['TH123_STOP_TEST_DIR'] = d
        env['TH123_STOP_TEST_MARKER'] = 'stopclean_marker_' + marker
        r = subprocess.run([sys.executable, '-X', 'utf8',
                            os.path.join(ROOT, 'tools',
                                         'train_stop_clean.py'),
                            '--timeout', '20'], capture_output=True,
                           text=True, env=env, timeout=120)
        check('stop_clean: exit=0', r.returncode == 0,
              'rc=%d out=%s' % (r.returncode, (r.stdout or '')[-120:]))
        time.sleep(1.5)
        alive = [p.pid for p in procs if p.poll() is None]
        check('stop_clean: main+control+watcher 全停', alive == [],
              str(alive))
        check('stop_clean: 标记文件存在',
              os.path.exists(os.path.join(d, 'train_stopped_clean')))
        check('stop_clean: 维护锁已释放',
              not os.path.exists(os.path.join(d,
                                              'fleet_maintenance.lock')))
        # watcher 未误恢复(无新 marker 进程)
        left = T.main_pids('stopclean_marker_' + marker)
        check('stop_clean: 无残留/无误恢复', left == [], str(left))
    finally:
        for p in procs:
            try:
                p.kill()
            except OSError:
                pass


def test_live_required():
    """无 --live 真停必须被拒绝(exit 3); --help 暴露 --live."""
    import subprocess
    r = subprocess.run([sys.executable, '-X', 'utf8',
                        os.path.join(ROOT, 'tools', 'train_stop_clean.py')],
                       capture_output=True, text=True, timeout=60)
    check('--live 硬门: 无 --live 拒绝真停(exit3)', r.returncode == 3,
          'rc=%d out=%s' % (r.returncode, (r.stdout or '')[-80:]))
    h = subprocess.run([sys.executable, '-X', 'utf8',
                        os.path.join(ROOT, 'tools', 'train_stop_clean.py'),
                        '--help'], capture_output=True, text=True,
                       timeout=60)
    check('--live 参数存在', '--live' in (h.stdout or ''))
    r2 = subprocess.run([sys.executable, '-X', 'utf8',
                         os.path.join(ROOT, 'tools', 'train_stop_clean.py'),
                         '--live', '--assume-locked'],
                        capture_output=True, text=True, timeout=60)
    check('--assume-locked 无锁→拒绝(exit6)', r2.returncode == 6,
          'rc=%d' % r2.returncode)


def test_dry_run_no_kill():
    d = tempfile.mkdtemp(prefix='stop_dry_')
    marker = uuid.uuid4().hex[:8]
    p = _spawn('main learner_hub', marker)
    time.sleep(1.5)
    try:
        env = dict(os.environ)
        env['TH123_STOP_TEST_DIR'] = d
        env['TH123_STOP_TEST_MARKER'] = 'stopclean_marker_' + marker
        r = subprocess.run([sys.executable, '-X', 'utf8',
                            os.path.join(ROOT, 'tools',
                                         'train_stop_clean.py'),
                            '--dry-run'], capture_output=True, text=True,
                           env=env, timeout=60)
        check('dry-run: exit=0', r.returncode == 0)
        check('dry-run: 进程仍存活', p.poll() is None)
    finally:
        p.kill()


def main():
    test_stop_clean_real()
    test_live_required()
    test_dry_run_no_kill()
    print('\n==== train_stop_clean: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
