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

    # ===== 构建产物完整性 =====
    for ch in ('reimu', 'marisa', 'suika'):
        p = os.path.join(OUT_DIR, '%s_index.npz' % ch)
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

    # ===== 查询语义 =====
    idx = query('reimu', matchup=11, near=True, attack=True, k=100)
    check('查询sakuya近距攻击情境', idx is not None and 0 < len(idx) <= 100,
          'n=%s' % (len(idx) if idx is not None else '-'))
    idx_all = query('reimu', k=0)
    check('k=0全量', idx_all is not None and len(idx_all) == 429411)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
