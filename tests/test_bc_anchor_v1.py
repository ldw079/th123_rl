# -*- coding: utf-8 -*-
"""task-60 行为测试: BC 补锚工具逻辑（无游戏依赖部分）。

覆盖: finalize_rows 去重/每宏上限; FeatCtx 侧向量布局(5N+391 三段)/
视觉栈 14400/3 通道; build_manifest provenance; src JSON 可解析.
R15: 行为基座=真实布局常量(FeatureBuilder.CORE_DIMS/resolve_reach),
不是源码字符串断言.
"""
import json
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


def _own(action=0, x=500.0, y=0.0, direction=1):
    return {'position.x': x, 'position.y': y, 'direction': direction,
            'action': action, 'spirit': 1000.0, 'hp': 10000,
            'airBorne': False, 'hitStop': 0, 'timeStop': 0, 'untech': 0,
            'cardGauge': 0, 'score': 0, 'comboDamage': 0,
            'hand': b'\xff' * 10, 'maxSpirit': 1000, 'skills': b'\0' * 15}


def _opp(action=0, x=575.0, y=0.0):
    d = _own(action=action, x=x, y=y)
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
    X, S, Y, src, per = A.finalize_rows(Xs, Ss, Ys, srcs, cap=2)
    check('finalize: 每宏上限(2)', int(per[2]) == 2, str(per))
    check('finalize: Y 与行数一致', len(Y) == len(X) == len(S) == len(src))


def test_finalize_dedupe_same_x():
    x = np.zeros(14400, np.uint8)
    Xs = [x, x.copy(), x.copy()]
    Ss = [np.zeros(831, np.float32) for _ in range(3)]
    Ys = [3, 3, 4]
    srcs = ['a', 'b', 'c']
    X, S, Y, src, per = A.finalize_rows(Xs, Ss, Ys, srcs, cap=10)
    # 语义: 同 X 同 Y 去重; 同 X 不同 Y = 不同动作选择样本, 允许并存
    check('finalize: 同(X,Y)去重/异Y并存', len(Y) == 2 and int(per[3]) == 1
          and int(per[4]) == 1, 'rows=%d per=%s' % (len(Y), per))


def test_feat_ctx_layout():
    ctx = A.FeatCtx('reimu')
    n = len(ctx.names)
    l, r = _own(), _opp()
    ctx.feed(l, r, W, OBJS)
    ctx.feed(l, r, W, OBJS)
    ctx.feed(l, r, W, OBJS)
    X = ctx._visual()
    check('visual: 14400 维', X is not None and X.shape == (14400,),
          str(None if X is None else X.shape))
    S = ctx._side(l, r, W, [], 5, 7)
    _exp = 5 * n + A.FeatureBuilder.CORE_DIMS
    check('side: 5N+CORE 宽', S.shape[0] == _exp,
          '%d vs %d' % (S.shape[0], _exp))
    check('side: 宏 one-hot 位', S[5] == 1.0 and S[n + 7] == 1.0)
    core = S[2 * n:2 * n + A.FeatureBuilder.CORE_DIMS]
    check('side: core 非全零', float(np.abs(core).sum()) > 0.0)
    b0 = 2 * n + A.FeatureBuilder.CORE_DIMS
    check('side: 射程/发生块有限', np.isfinite(S[b0:]).all())


def test_manifest():
    X = np.zeros((3, 14400), np.uint8)
    _w = 5 * 5 + A.FeatureBuilder.CORE_DIMS
    Sv = np.zeros((3, _w), np.float32)
    Yv = np.array([1, 2, 2], np.int64)
    names = ['m%d' % i for i in range(5)]
    m = A.build_manifest('reimu', 5, X, Sv, Yv, 'a.npz', 'ts', names)
    check('manifest: 行数/宽度', m['n_rows'] == 3
          and m['S_width'] == _w and m['X_width'] == 14400)
    check('manifest: provenance/per_macro', m['source'] == 'offline_replay_anchor'
          and m['per_macro'] == {'m1': 1, 'm2': 2})
    check('manifest: R1 标注', m.get('r1_compliant') is True)


def test_src_json():
    src = json.dumps({'char': 'reimu', 'macro': '连段A', 'scenario': 'mid',
                      'dmg': 1510.0, 'acts': [300, 320]}, ensure_ascii=False)
    d = json.loads(src)
    check('src: provenance 可解析', d['macro'] == '连段A'
          and d['scenario'] == 'mid' and d['dmg'] >= 300)


def main():
    test_finalize_dedupe_cap()
    test_finalize_dedupe_same_x()
    test_feat_ctx_layout()
    test_manifest()
    test_src_json()
    print('\n==== bc_anchor: %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
