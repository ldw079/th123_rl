# -*- coding: utf-8 -*-
"""E: supervisor boot 首拍心跳 (不改变后续行为)."""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import fleet_supervisor as FS  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    d = tempfile.mkdtemp(prefix='boot_hb_')
    FS.HEARTBEAT = os.path.join(d, 'hb')
    t0 = time.time()
    FS.boot_heartbeat()
    check('boot_heartbeat 写文件', os.path.exists(FS.HEARTBEAT))
    try:
        v = float(open(FS.HEARTBEAT).read())
        check('boot_heartbeat 时间戳有效', v >= t0 - 1)
    except Exception as e:
        check('boot_heartbeat 时间戳有效', False, repr(e))
    check('boot_heartbeat 无 alert 副作用',
          not os.path.exists(FS.HEARTBEAT + '.alert'))
    print('\n==== supervisor_boot_heartbeat: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
