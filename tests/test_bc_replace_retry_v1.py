# -*- coding: utf-8 -*-
"""BC replace retry 行为测试: 占用→重试成功; 持续占用→抛错回滚."""
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import bc_anchor_merge as M  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    d = tempfile.mkdtemp(prefix='bcretry_')
    src = os.path.join(d, 'src.npy')
    dst = os.path.join(d, 'dst.npy')
    open(src, 'wb').write(b'new')
    open(dst, 'wb').write(b'old')
    # 1) 占用 0.6s 后释放 -> retry 成功
    f = open(dst, 'rb')
    def rel():
        time.sleep(0.6)
        try:
            f.close()
        except OSError:
            pass
    threading.Thread(target=rel, daemon=True).start()
    ok = False
    try:
        M._replace_retry(src, dst, attempts=5, delay=0.2)
        ok = open(dst, 'rb').read() == b'new'
    except Exception as e:
        print('unexpected', repr(e))
    check('replace retry: 占用释放后成功', ok)
    # 2) 持续占用 -> 抛错
    open(src, 'wb').write(b'new2')
    open(dst, 'wb').write(b'old2')
    f2 = open(dst, 'rb')
    raised = False
    try:
        M._replace_retry(src, dst, attempts=2, delay=0.1)
    except RuntimeError:
        raised = True
    finally:
        f2.close()
    check('replace retry: 持续占用→抛错(可回滚)', raised)
    print('\n==== bc_replace_retry: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
