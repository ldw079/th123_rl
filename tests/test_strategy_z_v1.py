# -*- coding: utf-8 -*-
"""task-80 z 接口测试: env0 不变/解析/非法禁用."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import strategy_z as Z  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    old = os.environ.get('TH123_STRATEGY_Z')
    try:
        os.environ.pop('TH123_STRATEGY_Z', None)
        check('默认 env0→disabled', Z.enabled() is False)
        check('env0 condition=None(旧行为)', Z.condition() is None)
        os.environ['TH123_STRATEGY_Z'] = '0.7,0.8,0.2,0.5,0.4,0.3'
        z = Z.condition()
        check('合法 z 解析 6 维', isinstance(z, dict) and len(z) == 6
              and z['goal_push'] == 0.8)
        os.environ['TH123_STRATEGY_Z'] = '0.7,0.8'
        check('维度不足→None(禁静默)', Z.condition() is None)
        os.environ['TH123_STRATEGY_Z'] = '1.7,0,0,0,0,0'
        check('越界→None', Z.condition() is None)
    finally:
        if old is None:
            os.environ.pop('TH123_STRATEGY_Z', None)
        else:
            os.environ['TH123_STRATEGY_Z'] = old
    print('\n==== strategy_z: %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
