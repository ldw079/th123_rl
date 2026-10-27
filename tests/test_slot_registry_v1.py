# -*- coding: utf-8 -*-
"""W4 slot registry 骨架测试: env0 等价/旧 id 保留/C=256/追加/旧模型兼容."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import slot_registry as SR  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    old = os.environ.get('TH123_SLOT_REGISTRY')
    try:
        os.environ.pop('TH123_SLOT_REGISTRY', None)
        check('默认 env0→disabled', SR.enabled() is False)
        macros = ['m%d' % i for i in range(88)]
        idm = SR.identity_map(macros)
        check('env0 identity 旧映射不变',
              all(idm[i] == macros[i] for i in range(88)))
        reg, man = SR.build(macros, ['newA', 'newB'])
        check('旧 id 0..87 保留', all(reg[i] == macros[i] for i in range(88)))
        check('新宏填 88/89', reg[88] == 'newA' and reg[89] == 'newB')
        check('容量 256', man['capacity'] == 256 and len(reg) == 90)
        check('manifest added/旧id标记', man['old_ids_preserved']
              and len(man['added']) == 2)
        check('旧模型 n_out<=256 兼容', SR.validate_model_compat(95) is True)
        bad = False
        try:
            SR.validate_model_compat(300)
        except ValueError:
            bad = True
        check('n_out>256 拒绝', bad)
        # 容量满拒绝
        full = ['x%d' % i for i in range(256)]
        blocked = False
        try:
            SR.build(full, ['overflow'])
        except ValueError:
            blocked = True
        check('容量满追加拒绝(不截断)', blocked)
    finally:
        if old is None:
            os.environ.pop('TH123_SLOT_REGISTRY', None)
        else:
            os.environ['TH123_SLOT_REGISTRY'] = old
    print('\n==== slot_registry: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
