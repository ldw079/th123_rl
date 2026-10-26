# -*- coding: utf-8 -*-
"""P1 unknown snapshot 行为测试: 空/连续空/真实缺员区分."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import fleet_health as FH  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    # 1) snapshot 失败→None（monkeypatch _ps_json 返回空）
    orig = FH._ps_json
    FH._ps_json = lambda s: ''
    FH.snapshot = lambda marker=None, retries=1, delay=0: None
    ok, d = FH.check(snap=None, hb_age=1.0)
    check('unknown: snapshot None→bad unknown', (not ok) and
          d.get('unknown') and any('unknown' in x for x in d['bad']), str(d))
    # 2) unknown 不判 critical
    check('unknown: critical_snapshot=False', FH.critical_snapshot(None) is False)
    # 3) 真实缺员仍 critical
    real = {'sup': 0, 'learners': 3, 'actors': 3, 'ctl': 2, 'games': 4}
    check('real missing: critical=True', FH.critical_snapshot(real) is True)
    # 4) loop_tick unknown→不触发恢复
    calls = []
    def snap_fn():
        return None
    def launch_fn():
        calls.append(1)
    st = {}
    ok2, d2, acts = FH.loop_tick(st, now=1000.0, snap_fn=snap_fn,
                                 launch_fn=launch_fn, auto_recover=True)
    check('loop_tick unknown: no recover', (not ok2) and
          'unknown_snapshot' in acts and calls == [], str(acts))
    FH._ps_json = orig
    print('\n==== fleet_snapshot_unknown: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
