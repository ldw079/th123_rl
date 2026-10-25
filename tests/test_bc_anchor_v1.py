# -*- coding: utf-8 -*-
"""task-60 v2 行为测试: BC 补锚（P0-1 泄漏检查/历史 one-hot/combo 判据/去重/manifest）。

R15: 行为基座=真实布局(FeatureBuilder.CORE_DIMS/resolve_*)+因果历史语义，
不是源码字符串断言。游戏相关 blind replay 由 tools/bc_anchor_verify.py 产出独立证据。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import bc_anchor_collect as A  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _own(action=0, x=500.0):
    return {'position.x': x, 'position.y': 0.0, 'direction': 1,
            'action': action, 'spirit': 1000.0, 'hp': 10000,
            'airBorne': False, 'hitStop': 0, 'timeStop': 0, 'untech': 0,
            'cardGauge': 0, 'score': 0, 'comboDamage': 0,
            'hand': b'\xff' * 10, 'maxSpirit': 1000, 'skills': b'\0' * 15}


def _opp(action=0, x=575.0):
    d = _own(action=action, x=x)
    d['direction'] = -1
    d['hp'] = 9800
    return d


W = {'active': 0, 'displayed': 0, 'timer': 0}
OBJS = [[1, 540.0, 100.0, 0, 0, 0, 5]]


def test_finalize_dedupe_cap():
    Xs = [np.full(14400, i, np.uint8) for i in range(6)]
    Ss = [np.zeros(831, np.float32) for _ in range(6)]
    Ys = [1, 1, 2, 2, 2, 2]
    srcs = ['a', 'b', 'c', 'd', 'e', 'f']
    X, S, Y, src, per, conflicts = A.finalize_rows(Xs, Ss, Ys, srcs, cap=2)
    check('finalize: 每宏上限(2)', int(per[2]) == 2, str(per))
    check('finalize: 行数一致', len(Y) == len(X) == len(S) == len(src))


def test_finalize_conflict():
    x = np.zeros(14400, np.uint8)
    Xs = [x, x, x]
    Ss = [np.zeros(831, np.float32) for _ in range(3)]
    Ys = [3, 3, 4]
    srcs = ['a', 'b', 'c']
    X, S, Y, src, per, conflicts = A.finalize_rows(Xs, Ss, Ys, srcs, cap=10)
    check('finalize: 同(X,Y)去重/异Y并存', len(Y) == 2)
    check('finalize: same-X 多 Y 冲突计数', conflicts == 1, str(conflicts))


def test_no_target_leak_helper():
    ctx = A.FeatCtx('reimu')
    n = ctx.n
    S = ctx._side(_own(), _opp(), W, [])
    ok = A.assert_no_target_leak(S, n, 45)
    check('P0-1: target 宏不在 S 宏槽', ok is True)
    S2 = S.copy()
    S2[45] = 1.0
    raised = False
    try:
        A.assert_no_target_leak(S2, n, 45)
    except RuntimeError:
        raised = True
    check('P0-1: 泄漏样本被拒绝', raised)


def test_history_onehot():
    ctx = A.FeatCtx('reimu')
    n = ctx.n
    S = ctx._side(_own(), _opp(), W, [])
    idle = ctx.idle_idx
    check('历史 one-hot=待机(决策前)', S[idle] == 1.0 and S[n + idle] == 1.0)
    check('历史不含 target(随机宏)',
          all(S[j] == 0.0 for j in (5, 45, n + 5)))


def test_combo_ok_boundary():
    check('combo_ok: 300dmg+2acts', A.combo_ok(300.0, [300, 320]))
    check('combo_ok: <300dmg 拒绝', not A.combo_ok(299.9, [300, 320]))
    check('combo_ok: 1 act 拒绝', not A.combo_ok(500.0, [300]))
    check('combo_ok: 0 dmg 拒绝', not A.combo_ok(0.0, [300, 320, 321]))


def test_rle():
    seq = [{'A': True}, {'A': True}, {'H': -1}, {}]
    r = A.rle_compress(seq)
    check('RLE: 段数=3', len(r) == 3, str(r))
    check('RLE: 帧数合计=4', sum(x[1] for x in r) == 4)


def test_manifest_fields():
    X = np.zeros((3, 14400), np.uint8)
    _w = 5 * 5 + A.FeatureBuilder.CORE_DIMS
    Sv = np.zeros((3, _w), np.float32)
    Yv = np.array([1, 2, 2], np.int64)
    names = ['m%d' % i for i in range(5)]
    m = A.build_manifest('reimu', 5, X, Sv, Yv, 'a.npz', 'ts', names,
                         {'heldout_consistency': {'rate': 1.0}})
    check('manifest: 哈希/命令/泄漏检查字段',
          all(k in m for k in ('hashes', 'gen_cmd', 'verify_cmd',
                               'target_leak_check', 'heldout_consistency')))
    check('manifest: 宽度/行数', m['n_rows'] == 3 and m['S_width'] == _w)


def main():
    test_finalize_dedupe_cap()
    test_finalize_conflict()
    test_no_target_leak_helper()
    test_history_onehot()
    test_combo_ok_boundary()
    test_rle()
    test_manifest_fields()
    print('\n==== bc_anchor v2: %d PASS / %d FAIL ====' % (len(PASS),
                                                          len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
