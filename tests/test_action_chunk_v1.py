# -*- coding: utf-8 -*-
"""task-72 chunk 骨架测试: env0 不改变/宏/残差 chunk/校验."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import action_chunk as AC  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    old = os.environ.get('TH123_ACTION_CHUNK')
    try:
        os.environ.pop('TH123_ACTION_CHUNK', None)
        check('默认 env0→disabled', AC.enabled() is False)
        check('env0 不构造 chunk', AC.build_if_enabled(
            'macro', slot=5, frames=8) is None)
        os.environ['TH123_ACTION_CHUNK'] = '1'
        check('env1 enabled', AC.enabled() is True)
        c = AC.build_if_enabled('macro', slot=5, frames=8,
                                interrupt_at=[0, 4])
        check('macro chunk 构造/校验', c is not None and AC.validate(c))
        r = AC.build_if_enabled('resid', resid_seq=[1, 2, 3])
        check('resid chunk frames=3', r is not None and r['frames'] == 3)
        bad = False
        try:
            AC.make_resid_chunk([])
        except ValueError:
            bad = True
        check('空 resid 拒绝', bad)
        bad2 = False
        try:
            badc = AC.make_resid_chunk([1, 2, 3])
            badc['frames'] = 5
            AC.validate(badc)
        except ValueError:
            bad2 = True
        check('resid/frames 不一致拒绝', bad2)
    finally:
        if old is None:
            os.environ.pop('TH123_ACTION_CHUNK', None)
        else:
            os.environ['TH123_ACTION_CHUNK'] = old
    print('\n==== action_chunk: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
