# -*- coding: utf-8 -*-
"""task-69 harness MVP 测试: R1 只写己方; BoN 摘要; 快照 hash."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import human_match_harness as H  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    import tempfile
    d = tempfile.mkdtemp(prefix='hmh_')
    h = H.HumanMatchHarness(bo=3, seed=1, snapshot='snapA', out_dir=d)
    summ, p, rp = h.run()
    check('Bo3 局数', summ['games'] == 3)
    check('只记录己方输入(R1)', summ['r1'] == 'only_own_inputs'
          and summ['forbidden_reads'] == 0)
    check('己方输入数>0', summ['own_inputs'] > 0)
    check('快照 hash 冻结', len(summ['snapshot_hash']) == 16)
    check('摘要文件写出', os.path.exists(p) and os.path.exists(rp))
    # R1 哨兵: 读对手必须抛错
    blocked = False
    try:
        h._try_read_opponent()
    except PermissionError:
        blocked = True
    check('R1: 读对手输入被拒绝', blocked and h.forbidden_reads == 1)
    print('\n==== human_match_harness: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
