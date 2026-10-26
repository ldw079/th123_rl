# -*- coding: utf-8 -*-
"""R15: episode retention archive (TH123_EP_KEEP)."""
import glob
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import episode_core as E  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    d = tempfile.mkdtemp(prefix='epkeep_')
    keep = os.path.join(d, 'keep')
    # 5 个文件，依次 archive，keep_n=3 → 保留最近 3
    for i in range(5):
        p = os.path.join(d, 'ep_%d.npz' % i)
        open(p, 'wb').write(b'x')
        ok = E.archive_episode(p, keep, 3)
        check('archive %d 成功' % i, ok)
        time.sleep(0.01)
    left = sorted(os.path.basename(x) for x in glob.glob(os.path.join(keep, '*.npz')))
    check('keep 保留最近3个', left == ['ep_2.npz', 'ep_3.npz', 'ep_4.npz'], str(left))
    check('原文件已移走(不残留)', not glob.glob(os.path.join(d, 'ep_*.npz')))
    print('\n==== episode_retention: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
