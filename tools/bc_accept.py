# -*- coding: utf-8 -*-
"""P0-6 重建验收探针(一次性, 走完即删 — 「探针不留残档」)。

用途: 三库重建完成 → 换装前, 证明 SC 修复真的落到产物上:
  1. 三个复合宏(TM·6a终结/TM·必杀SC连/TM·空连终结)在对应角色库中 Y 计数 > 0;
  2. 换装前(v3 目录) 与 换装后(store trio) 双侧读数一致;
  3. 行数/宽度与代码派生值一致(5N+CORE_DIMS)。

用法:
  python tools/_p0_6_accept.py --where v3      # 换装前: 读 D:\\temp\\th123_bc_v3\\*.npz
  python tools/_p0_6_accept.py --where store   # 换装后: 读 STORE/bc_<ch>_Y.npy
"""
import argparse
import io
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')


def _libs():
    from train_tm import CHAR_LIBS
    return CHAR_LIBS


def _check(char, Y, S_w, rows, where, out):
    from feat_builder import FeatureBuilder
    lib = _libs()[char]['macros']
    idx = {m[0]: i for i, m in enumerate(lib)}
    want_w = 5 * len(lib) + FeatureBuilder.CORE_DIMS
    tgt = ('TM·6a终结', 'TM·必杀SC连', 'TM·空连终结')
    cnt = {n: (int((Y == idx[n]).sum()) if n in idx else None) for n in tgt}
    ok_w = (S_w == want_w)
    nz = [n for n, c in cnt.items() if c]
    present = [n for n in tgt if cnt[n] is not None]
    ok_sc = bool(nz) and len(nz) == len(present)   # 该角色存在的复合宏必须都有计数
    out.append({
        'char': char, 'where': where, 'rows': int(rows), 'S_width': int(S_w),
        'want_width': int(want_w), 'width_ok': ok_w,
        'composite_macros': present, 'Y_counts': cnt, 'sc_ok': ok_sc,
    })
    tag = '✓' if (ok_w and ok_sc) else '✗'
    print('%s %-7s [%s] rows=%-7d S=%-4d(want %d) 复合宏=%s Y=%s'
          % (tag, char, where, rows, S_w, want_w, present, cnt))
    return ok_w and ok_sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--where', default='v3', choices=['v3', 'store'])
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
    out, allok = [], True
    for char in ('reimu', 'marisa', 'suika'):
        if a.where == 'v3':
            p = os.path.join(r'D:\temp\th123_bc_v3', 'bc_%s_v3.npz' % char)
            if not os.path.exists(p):
                print('✗ %-7s 缺产物 %s' % (char, p))
                allok = False
                continue
            d = np.load(p, allow_pickle=True)
            Y = np.asarray(d['Y'])
            allok &= _check(char, Y, d['S'].shape[1], Y.shape[0], 'v3', out)
        else:
            yp = os.path.join(store, 'bc_%s_Y.npy' % char)
            sp = os.path.join(store, 'bc_%s_S.npy' % char)
            if not (os.path.exists(yp) and os.path.exists(sp)):
                print('✗ %-7s 缺 trio 档' % char)
                allok = False
                continue
            Y = np.asarray(np.load(yp, mmap_mode='r'))
            S_w = np.load(sp, mmap_mode='r').shape[1]
            allok &= _check(char, Y, S_w, Y.shape[0], 'store', out)
    if a.json:
        io.open(a.json, 'w', encoding='utf8').write(
            json.dumps({'all_ok': bool(allok), 'items': out},
                       ensure_ascii=False, indent=1))
        print('报告:', a.json)
    print('\n==== 验收 %s ====' % ('通过' if allok else '未通过'))
    return 0 if allok else 1


if __name__ == '__main__':
    sys.exit(main())
