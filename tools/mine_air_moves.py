# -*- coding: utf-8 -*-
"""空中按钮→move id实测映射挖掘(R26): oracle帧流里, 滞空(airBorne)时
触发的攻击move — 滞空过滤天然排除地面冲刺污染(306问题)。只挖A系
空中体术(jA/j6A/j8A/j2A), 按键上升沿锚定。
产出: data/air_move_hints_<char>.json + 置信度清单(低票/冲突项留给
用户核实 — 用户2026-10-02"拿不准的数据我来想办法")。
用法: python tools/mine_air_moves.py [max_shards]"""
import glob
import json
import os
import sys
from collections import Counter

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.stdout.reconfigure(encoding='utf8')
from bc_build import build_shard, mirror_frames  # noqa: E402
from action_tables import CHAR_ACTION_TABLES as T  # noqa: E402

# P0-2(从零#5): 路径取仓库相对(原 用户家目录宏 字面量只在本机成立)
SHARDS = sorted(glob.glob(os.path.join(
    os.environ.get('TH123_ORACLE_SHARDS')
    or os.path.join(_REPO, 'data', 'oracle_v2', 'shards'), '*.npz')))
CHAR_IDS = {'reimu': 0, 'marisa': 1, 'suika': 9}
OUT = os.path.join(_REPO, 'data')
AIR_SIGS = ('A|0|0', 'A|1|0', 'A|0|1', 'A|0|-1')   # jA/j6A/j8A/j2A


def sig_of(u):
    btns = ''.join(sorted(n for b, n in ((1, 'A'), (2, 'B'), (4, 'C'),
                                         (8, 'D')) if u & b))
    h = 1 if (u >> 6) & 3 == 1 else 0
    v = {0: 0, 1: 1, 2: 0, 3: -1}[(u >> 8) & 3]
    return '%s|%d|%d' % (btns, h, v)


def main():
    mx = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    votes = {ch: Counter() for ch in CHAR_IDS}
    conflict = {ch: Counter() for ch in CHAR_IDS}
    atk_all = {ch: T[ch]['attack'] for ch in CHAR_IDS}
    n_sh = 0
    for sp in SHARDS[:mx * 2]:
        if n_sh >= mx:
            break
        try:
            meta, frames, inputs = build_shard(sp)
        except Exception:
            continue
        if inputs.ndim != 2 or len(inputs) < 200:
            continue
        if meta['char_x'] not in CHAR_IDS.values() \
                and meta['char_y'] not in CHAR_IDS.values():
            continue
        n_sh += 1
        for side in (0, 1):
            cx = meta['char_x'] if side == 0 else meta['char_y']
            ch = [k for k, v in CHAR_IDS.items() if v == cx]
            if not ch:
                continue
            ch = ch[0]
            if side == 0:
                fr, u16 = frames, inputs[:, 1]
            else:
                fr, u16 = mirror_frames(frames, inputs)
            n = min(len(fr), len(u16))
            for j in range(2, n - 25):
                uj, uj1 = int(u16[j]), int(u16[j - 1])
                if not (uj & 1) or (uj1 & 0xF):     # A上升沿
                    continue
                if not fr[j][0].get('airBorne'):
                    continue
                s = sig_of(uj)
                if s not in AIR_SIGS:
                    continue
                for k in range(j, j + 22):
                    if not fr[k][0].get('airBorne'):
                        break                          # 落地了, 放弃
                    a = fr[k][0].get('action', 0) or 0
                    a0 = fr[k - 1][0].get('action', 0) or 0
                    if a in atk_all[ch] and a0 not in atk_all[ch]:
                        a2 = fr[k + 1][0].get('action', 0) or 0 \
                            if k + 1 < n else 0
                        if a2 == a:
                            votes[ch][(s, a)] += 1
                        break
    for ch in CHAR_IDS:
        best = {}
        for (s, a), n in votes[ch].items():
            if n > best.get(s, (None, 0))[1]:
                best[s] = (a, n)
        out = {}
        uncertain = []
        for s in AIR_SIGS:
            if s not in best:
                uncertain.append('%s: 无观测' % s)
                continue
            a, n = best[s]
            # 冲突检测: 该签名的前两名票数接近
            all_v = sorted((nn for (ss, _aa), nn in votes[ch].items()
                            if ss == s), reverse=True)
            if len(all_v) > 1 and all_v[1] >= all_v[0] * 0.5:
                uncertain.append('%s: 冲突%s票数%s' % (s, all_v[:3], a))
            elif n < 5:
                uncertain.append('%s: 低票%d' % (s, n))
            out[s] = a
        p = os.path.join(OUT, 'air_move_hints_%s.json' % ch)
        json.dump(out, open(p, 'w'), ensure_ascii=False, indent=1)
        print('==== %s (%d分片) ====' % (ch, n_sh))
        sig2name = {'A|0|0': 'jA', 'A|1|0': 'j6A', 'A|0|1': 'j8A',
                    'A|0|-1': 'j2A'}
        for s, a in sorted(out.items()):
            r, rv = T[ch]['reach'].get(a, 0), T[ch]['reach_v'].get(a, 0)
            print('  %-4s → move %d (reach %d×%d, %d次)'
                  % (sig2name.get(s, s), a, r, rv, best[s][1]))
        for u in uncertain:
            print('  ?? %-4s %s' % (sig2name.get(s, s), u))


if __name__ == '__main__':
    main()
