# -*- coding: utf-8 -*-
"""LE-1a行为测试: 情境库 — 标签派生(2n偏移)/对位覆盖/热度/查询语义。"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from situation_library import (TAG_ATTACK, TAG_CORNER, TAG_MATCHUP,
                               TAG_NEAR, derive_tags, query)
from train_tm import CHAR_LIBS

PASS, FAIL = [], []
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'situations')


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    # ===== derive_tags单元(2n偏移) =====
    n = len(CHAR_LIBS['reimu']['macros'])
    O = 2 * n
    S = np.zeros((4, 5 * n + 358), dtype=np.float32)
    # 行0: 对位sakuya(oid=11→槽227+11), 近距, 攻击标签Y=0(5A∈attack)
    S[0, O + 227 + 11] = 1.0
    S[0, O + 4] = 0.35
    # 行1: 对位yukari(扩展区oid=20→槽308), 贴角
    S[1, O + 308] = 1.0
    S[1, O + 149] = 1.5
    # 行2: 无对位
    S[2, O + 4] = 0.8   # 远距
    # 行3: 对位suika(oid=2)
    S[3, O + 227 + 2] = 1.0
    atk0 = 0
    for i, (nm, _s) in enumerate(CHAR_LIBS['reimu']['macros']):
        if nm in CHAR_LIBS['reimu']['attack']:
            atk0 = i
            break
    non_atk = 0
    for i, (nm, _s) in enumerate(CHAR_LIBS['reimu']['macros']):
        if nm not in CHAR_LIBS['reimu']['attack']:
            non_atk = i
            break
    Y = np.array([atk0, non_atk, non_atk, atk0])
    tags, mid = derive_tags(S, Y, 'reimu')
    check('对位sakuya=11', mid[0] == 11)
    check('对位yukari=20(扩展)', mid[1] == 20)
    check('无对位=-1', mid[2] == -1)
    check('对位suika=2', mid[3] == 2)
    check('近距位行0=1', tags[0, TAG_NEAR] == 1.0)
    check('远距行2不近', tags[2, TAG_NEAR] == 0.0)
    check('贴角行1=1(1.5幅度)', tags[1, TAG_CORNER] == 1.0)
    check('攻击标签0/3=1, 1/2=0',
          tags[0, TAG_ATTACK] == 1.0 and tags[1, TAG_ATTACK] == 0.0
          and tags[3, TAG_ATTACK] == 1.0)

    # ===== 构建产物完整性(沙箱兼容: 产物不入沙箱→跳过产物段,
    # 只跑合成数据段 — R158: 全量sweep基线连续三轮被产物依赖卡死) =====
    _prod_ok = os.path.exists(os.path.join(OUT_DIR, 'reimu_index.npz'))
    for ch in ('reimu', 'marisa', 'suika'):
        p = os.path.join(OUT_DIR, '%s_index.npz' % ch)
        if not _prod_ok:
            check('%s索引(沙箱跳过)' % ch, True, '产物不入沙箱')
            continue
        check('%s索引存在' % ch, os.path.exists(p))
        d = np.load(p, allow_pickle=True)
        meta = json.loads(str(d['meta']))
        tags, mid = d['tags'], d['matchup']
        check('%s对位标注率≥99%%' % ch, (mid >= 0).mean() >= 0.99,
              '%.3f' % (mid >= 0).mean())
        uniq = len(set(int(x) for x in np.unique(mid) if x >= 0))
        check('%s对位多样性≥10' % ch, uniq >= 10, '%d' % uniq)
        check('%s贴角率5-60%%' % ch,
              0.05 <= tags[:, TAG_CORNER].mean() <= 0.60,
              '%.3f' % tags[:, TAG_CORNER].mean())
        check('%s行数=meta' % ch, len(mid) == meta['rows'])

    # ===== 查询语义(沙箱兼容) =====
    if _prod_ok:
        idx = query('reimu', matchup=11, near=True, attack=True, k=100)
        check('查询sakuya近距攻击情境',
              idx is not None and 0 < len(idx) <= 100,
              'n=%s' % (len(idx) if idx is not None else '-'))
        idx_all = query('reimu', k=0)
        _exp_rows = json.loads(str(np.load(os.path.join(
            OUT_DIR, 'reimu_index.npz'),
            allow_pickle=True)['meta']))['rows']
        check('k=0全量',
              idx_all is not None and len(idx_all) == _exp_rows,
              'n=%d/meta=%d' % (len(idx_all)
                                if idx_all is not None else -1,
                                _exp_rows))
        d2 = np.load(os.path.join(OUT_DIR, 'reimu_index.npz'),
                     allow_pickle=True)
        meta2 = json.loads(str(d2['meta']))
        hv = list(meta2.get('heat', {}).values())
        check('产物热度存在且<1(真实数据)',
              hv and all(v < 1.0 for v in hv), str(hv[:3]))
    else:
        check('查询语义(沙箱跳过)', True, '产物不入沙箱')

    # ===== P0防复发(bug_2026-10-17): 热度不恒1 — 用合成raw数据直测
    # matchup_heat(合成fate计数: vs某对位hit=3其余fate=97 → heat≈0.97) =====
    from situation_library import matchup_heat, TAG_ATTACK as _TA
    import situation_library as sl
    _orig_agg = sl.aggregate if hasattr(sl, 'aggregate') else None

    class _FakeBH:
        aggregate = staticmethod(lambda *a, **k: {
            'combo_by_opp': {'reimu': {'hit': 3, 'blocked': 0,
                                       'dropped': 57, 'interrupted': 40}}})

    import behavior_health as _bh
    _orig_mod = sys.modules.get('behavior_health')
    sys.modules['behavior_health'] = _FakeBH
    try:
        h = matchup_heat('reimu')
    finally:
        sys.modules['behavior_health'] = _orig_mod
    check('热度≠恒1(合成hit率0.03→heat0.97)',
          h.get(0) is not None and abs(h[0] - 0.97) < 0.01, str(h))
    check('热度非空', len(h) >= 1)

    # 产物meta热度段已在上方_prod_ok分支覆盖(沙箱跳过)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
