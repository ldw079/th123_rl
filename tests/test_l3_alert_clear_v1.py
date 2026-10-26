# -*- coding: utf-8 -*-
"""L3 machine_alert 清除行为测试 (test file)."""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import fleet_supervisor as FS  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    d = tempfile.mkdtemp(prefix='l3_')
    FS.MACHINE_ALERT = os.path.join(d, 'fleet_heartbeat.machine_alert')
    io.open(FS.MACHINE_ALERT, 'w').write('{"msg":"machine>85"}')
    # 1) 仍有告警状态 → 不清
    FS._L3_STATE['m_hi'] = 3
    FS._L3_STATE['m_crit'] = 0
    check('L3: 仍高负载→不清 alert',
          FS.l3_clear_alert_if_recovered() is False
          and os.path.exists(FS.MACHINE_ALERT))
    # 2) 恢复(全 0) → 清除
    FS._L3_STATE['m_hi'] = 0
    FS._L3_STATE['m_crit'] = 0
    check('L3: 恢复→清 machine_alert',
          FS.l3_clear_alert_if_recovered() is True
          and not os.path.exists(FS.MACHINE_ALERT))
    # 3) 无文件→False 不抛
    check('L3: 无文件→False 不崩',
          FS.l3_clear_alert_if_recovered() is False)
    # 4) fleet_alert 不受影响
    fa = os.path.join(d, 'fleet_heartbeat.fleet_alert')
    io.open(fa, 'w').write('fleet')
    io.open(FS.MACHINE_ALERT, 'w').write('x')
    FS.l3_clear_alert_if_recovered()
    check('L3: 不清 fleet_alert', os.path.exists(fa))
    print('\n==== l3_alert_clear: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
