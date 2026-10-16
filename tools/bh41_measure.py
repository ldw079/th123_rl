# -*- coding: utf-8 -*-
"""BH-4.1度量环: 连段语境matcher改动的验收测量(方案判据:
对手真受击帧上攻击类标签 17-21% → ≥40%)。

同批分片×双侧 × (基线=无语境 | 治疗=combo_ctx) → 三口径:
  ①真受击帧标签中攻击类占比(主判据)
  ②真受击帧标签数(语境是否提升覆盖 — 侧面防"虚增")
  ③全帧标签攻击类占比(总体位移)
用法: python tools/bh41_measure.py [--shards 30]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')

from bc_build import LIBS, build_shard, mirror_frames, mirror_input
from bc_match import StreamMatcher
from feat_builder import HIT_ACT_IDS
from train_tm import CHAR_LIBS


def run(char_id, shards, use_ctx):
    name, lib = LIBS[char_id]
    atk = CHAR_LIBS[name]['attack']
    m = StreamMatcher(lib, threshold=0.88, attack_names=atk)
    n_hs = 0
    cls = Counter()
    for sp in shards:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if ilog is None or len(frames) < 100 or meta.get('err'):
            continue
        # ilog=(左u16, 右u16)元组
        u16L, u16R = ilog[0], ilog[1]
        for side in (0, 1):
            if side == 0 and meta.get('char_x') != char_id:
                continue
            if side == 1 and meta.get('char_y') != char_id:
                continue
            fr = frames if side == 0 else mirror_frames(frames)
            u16 = u16L if side == 0 else mirror_input(u16R)
            facings = [1 if f[0]['direction'] > 0 else -1 for f in fr]
            ctx = None
            if use_ctx:
                ctx = [(f[1].get('action', 0) in HIT_ACT_IDS
                        and abs(f[1]['position.x'] - f[0]['position.x'])
                        < 250) for f in fr]
            hits = m.walk(u16, facings, combo_ctx=ctx)
            hits = [h for h in hits if h[2] >= 0.88 and h[0] >= 2
                    and h[0] < len(fr)]
            for h in hits:
                f0 = h[0]
                mname = lib[h[1]][0]
                is_atk = mname in atk
                if fr[f0][1].get('action', 0) in HIT_ACT_IDS:
                    n_hs += 1
                    cls['hs_atk' if is_atk else 'hs_other'] += 1
                cls['atk' if is_atk else 'other'] += 1
    return n_hs, cls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shards', type=int, default=20,
                    help='文档口径=20(审计2026-10-16对齐)')
    ap.add_argument('--chars', default='reimu,marisa,suika')
    a = ap.parse_args()
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:a.shards]
    print('分片%d个(前%d个tr*分片)' % (len(shards), a.shards))
    for ch in a.chars.split(','):
        cid = next((c for c, (n, _l) in LIBS.items() if n == ch), None)
        if cid is None:
            continue
        n0, c0 = run(cid, shards, False)
        n1, c1 = run(cid, shards, True)
        hs0 = c0['hs_atk'] + c0['hs_other']
        hs1 = c1['hs_atk'] + c1['hs_other']
        r0 = c0['hs_atk'] / hs0 if hs0 else 0
        r1 = c1['hs_atk'] / hs1 if hs1 else 0
        print('%-7s 真受击帧标签: 基线%d(攻击%.1f%%) → 语境%d(攻击%.1f%%)'
              ' | 总标签攻击份额 %.1f%%→%.1f%%'
              % (ch, hs0, 100 * r0, hs1, 100 * r1,
                 100 * c0['atk'] / max(1, c0['atk'] + c0['other']),
                 100 * c1['atk'] / max(1, c1['atk'] + c1['other'])))


if __name__ == '__main__':
    main()
