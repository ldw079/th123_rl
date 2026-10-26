# -*- coding: utf-8 -*-
"""P1 probe 行为测试: dummy 不计数; 超数报警."""
import os
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import fleet_health as FH  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    base = FH.snapshot()
    dummy = subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(30)',
         'ar6dummy_' + uuid.uuid4().hex[:8], 'learner_hub'])
    try:
        time.sleep(1.5)
        snap = FH.snapshot()
        same = all(int(snap.get(k, -1)) == int(base.get(k, -1))
                   for k in ('sup', 'learners', 'actors', 'ctl', 'games'))
        check('probe: dummy(-c learner_hub) 不计数', same,
              'base=%s now=%s' % (base, snap))
    finally:
        dummy.kill()
    # 精确计数: 超数报警
    dup = {'sup': 1, 'learners': 6, 'actors': 3, 'ctl': 2, 'games': 4}
    ok, d = FH.check(snap=dup, hb_age=1.0)
    check('probe: learners 超数→bad(dup/extra)', (not ok) and
          any('dup/extra' in x for x in d['bad']), str(d['bad']))
    dup2 = {'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 4, 'games': 4}
    okd, dd = FH.check(snap=dup2, hb_age=1.0)
    check('probe: ctl 4>2→bad(dup/extra)', (not okd) and
          any('ctl' in x and 'dup' in x for x in dd['bad']), str(dd['bad']))
    good = {'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2, 'games': 4}
    ok2, d2 = FH.check(snap=good, hb_age=1.0)
    check('probe: 精确计数→PASS', ok2, str(d2['bad']))
    print('\n==== fleet_probe_exact: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
