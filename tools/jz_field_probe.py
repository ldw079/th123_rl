# -*- coding: utf-8 -*-
"""JZ-0 字段语义探针(系统机制补全方案2026-10-14, A档的门).

在oracle分片上离线验证四个未证实字段语义:
  1. airDashCount: 值域/空中消耗/落地重置(与airBorne/y对齐)
  2. skills 15字节: 槽位×等级布局
  3. maxSpirit: 单位与破珠对应(破珠事件=最大值下降)
  4. superArmorHp/healingCharm/confusion/swordOfRapture: 分布与场景

门规则: 语义未证实的字段不入JZ-1(不猜数据)。
产出: docs/_reviews/jz_field_semantics_probe_2026-10-14.md
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')

from bc_build import build_shard   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=120)
    ap.add_argument('--out', default=os.path.join(
        ROOT, 'docs', '_reviews', 'jz_field_semantics_probe_2026-10-14.md'))
    a = ap.parse_args()
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:a.limit]

    adc_vals = collections.Counter()
    adc_air = collections.Counter()      # (val, airBorne)
    adc_land_reset = [0, 0]              # [落地时重置为基值, 落地时未变]
    adc_consumed = 0                     # 空中val下降事件
    maxspirit_vals = collections.Counter()
    ms_drops = []                        # (帧, 旧, 新)
    skills_shapes = collections.Counter()
    skills_byte_vals = [collections.Counter() for _ in range(15)]
    status_nz = collections.Counter()    # 字段→非零帧数
    status_ctx = collections.defaultdict(collections.Counter)
    frames_tot = 0

    for sp in shards:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if len(frames) < 200:
            continue
        frames_tot += len(frames)
        for side, me in ((0, 0), (1, 1)):
            prev = None
            prev_air = False
            for f in frames:
                d = f[me]
                adc = d.get('airDashCount', -1)
                air = bool(d.get('airBorne', False))
                adc_vals[adc] += 1
                adc_air[(adc, air)] += 1
                if prev is not None:
                    if prev_air and not air:      # 落地帧
                        if adc == adc_base:
                            adc_land_reset[0] += 1
                        else:
                            adc_land_reset[1] += 1
                    if air and adc < prev_adc:
                        adc_consumed += 1
                prev_adc, prev_air = adc, air
                if prev is None:
                    adc_base = adc
                prev = d
                ms = d.get('maxSpirit', -1)
                maxspirit_vals[ms] += 1
                sk = d.get('skills', b'')
                if isinstance(sk, (bytes, bytearray)):
                    skills_shapes[len(sk)] += 1
                    if len(sk) == 15:
                        for i, b in enumerate(sk):
                            skills_byte_vals[i][b] += 1
                for k in ('superArmorHp', 'healingCharm',
                          'confusion', 'swordOfRapture'):
                    v = d.get(k, 0) or 0
                    if v:
                        status_nz[k] += 1
                        status_ctx[k][d.get('action', 0)] += 1

    L = []
    L.append('# JZ-0 字段语义探针(2026-10-14)')
    L.append('')
    L.append('数据: %d shards × 双侧, %d帧' % (len(shards), frames_tot))
    L.append('')
    # 1. airDashCount
    L.append('## 1. airDashCount')
    L.append('值域Top: %s' % adc_vals.most_common(8))
    by_air = collections.defaultdict(collections.Counter)
    for (v, air), c in adc_air.items():
        by_air[air][v] += c
    L.append('空中值域Top: %s' % by_air[True].most_common(5))
    L.append('地面值域Top: %s' % by_air[False].most_common(5))
    L.append('落地重置(回到地面基值): %d / 未变: %d'
             % tuple(adc_land_reset))
    L.append('空中下降事件(消耗): %d' % adc_consumed)
    # 2. maxSpirit
    L.append('')
    L.append('## 2. maxSpirit')
    L.append('值域: %s' % sorted(maxspirit_vals)[:12])
    L.append('下降事件数: %d (破珠候选)' % len(ms_drops))
    # 3. skills
    L.append('')
    L.append('## 3. skills 15字节')
    L.append('长度分布: %s' % dict(skills_shapes))
    for i in range(15):
        top = skills_byte_vals[i].most_common(3)
        if top and top[0][0] > 0:
            L.append('  byte%d: %s' % (i, top))
    # 4. 状态字段
    L.append('')
    L.append('## 4. 状态四字段')
    for k in ('superArmorHp', 'healingCharm', 'confusion',
              'swordOfRapture'):
        L.append('%s: 非零帧%d (%.3f%%) action伴生Top: %s'
                 % (k, status_nz[k], status_nz[k] / max(frames_tot * 2, 1)
                    * 100, status_ctx[k].most_common(4)))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, 'w', encoding='utf8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    print('\n报告: %s' % a.out)


if __name__ == '__main__':
    main()
