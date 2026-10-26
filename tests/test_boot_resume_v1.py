# -*- coding: utf-8 -*-
"""R15 行为/决策测试: boot_resume opt-in 逻辑 (Lead 10:03)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import boot_resume as BR  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    check('opt-in: 无标志→不恢复(flag_absent)',
          BR.should_resume(False, False, False) == (False, 'flag_absent'))
    check('opt-in: 有标志+无 sup+无锁→恢复',
          BR.should_resume(True, False, False) == (True, 'resume'))
    check('防重复: sup 已跑→跳过',
          BR.should_resume(True, True, False)
          == (False, 'supervisor_already_running'))
    check('维护锁: 有锁→跳过',
          BR.should_resume(True, False, True)
          == (False, 'maintenance_lock'))
    check('标志路径含 train_resume_on_boot',
          BR.FLAG.endswith('train_resume_on_boot'))
    # --check 行为: 标志缺失时退出码 1
    import subprocess
    r = subprocess.run([sys.executable, '-X', 'utf8',
                        os.path.join(ROOT, 'tools', 'boot_resume.py'),
                        '--check'], capture_output=True, text=True,
                       timeout=60)
    check('CLI --check: 标志缺失→exit1', r.returncode == 1,
          'rc=%d out=%s' % (r.returncode, (r.stdout or '')[-60:]))
    print('\n==== boot_resume: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
