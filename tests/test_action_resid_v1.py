# -*- coding: utf-8 -*-
"""task-71 骨架测试: 6键×9向×时长档; env=0 行为不变; 编解码一致."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import action_resid as AR  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    old = os.environ.get('TH123_ACT_RESID')
    try:
        os.environ.pop('TH123_ACT_RESID', None)
        check('默认 env 未设→disabled', AR.resid_enabled() is False)
        os.environ['TH123_ACT_RESID'] = '0'
        check('env=0→disabled', AR.resid_enabled() is False)
        base = 'macro:5A'
        check('env=0 行为不变(原样返回)',
              AR.apply_if_enabled(base, 0) == base)
        os.environ['TH123_ACT_RESID'] = '1'
        check('env=1→enabled', AR.resid_enabled() is True)
        check('动作空间 6*9*9=486', AR.N_ACTIONS == 486)
        ids = list(AR.all_actions())
        check('全部动作可枚举/唯一', len(ids) == 486 and len(set(ids)) == 486)
        ok = True
        for a in (0, 123, 485):
            k, d, du = AR.decode(a)
            if AR.encode(k, d, du) != a:
                ok = False
        check('编解码往返一致', ok)
        cov = AR.coverage(ids)
        check('coverage 100%', cov['rate'] == 1.0)
        res = AR.apply_if_enabled(base, 5)
        check('env=1 残差覆盖生效', isinstance(res, dict) and 'resid' in res)
    finally:
        if old is None:
            os.environ.pop('TH123_ACT_RESID', None)
        else:
            os.environ['TH123_ACT_RESID'] = old
    print('\n==== action_resid: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
