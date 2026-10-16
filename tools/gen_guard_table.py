# -*- coding: utf-8 -*-
"""BH-3.2(行为健康方案v4): 逐角色守备段位表生成器。

数据源: cleista api v1 逐招detail的 move.properties:
  blockLow=必须蹲防(下段) blockHigh=必须站防(中段/上段)
  (detail档由bash curl批量预取到 data/guide_tables/cleista/detail/)

输出: data/guide_tables/guard_height.json
  low:  {char: [action IDs]}  — 蹲防必(对手出这些ID时我方须蹲防)
  high: {char: [action IDs]}  — 站防必(文档性登记; 冻结期不加特征位)
  per_move: 逐招出处(可审计)

ID映射(docs/soku_action_ids.md SokuLib枚举, 300-330/400-418引擎公共):
  2a→303+311(f.2A远近同页) 3a→304 2b→402 2c→412 6b→401 66b→408
  j2a→308; suwako 3a→331(SUWAKO_3A专属)
必杀5xx"无法从招名得知ID"(docs明示) — 不入表(R4: 空映射优于错映射)。
"""
from __future__ import annotations

import glob
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.stdout.reconfigure(encoding='utf8')

DETAIL_DIR = os.path.join(ROOT, 'data', 'guide_tables', 'cleista',
                          'detail')
OUT = os.path.join(ROOT, 'data', 'guide_tables', 'guard_height.json')

SLUG_IDS = {
    '2a': [303, 311],   # 2A + f.2A(远近变体同守备, 无独立detail页)
    '3a': [304],
    '2b': [402],
    '2c': [412],
    '6b': [401],
    '66b': [408],
    'j2a': [308],
}
SUWAKO_OVERRIDE = {'3a': [331]}   # ACTION_SUWAKO_3A(角色专属)


def main():
    # 索引校验集: 该角色确有的slug(防"无效招的错误响应"混入 —
    # suwako无2A/yukari·yuyuko无6B, 直取URL回404页非JSON)
    index_slugs = {}
    for ipath in glob.glob(os.path.join(
            ROOT, 'data', 'guide_tables', 'cleista', 'api', '*.json')):
        ch = os.path.basename(ipath)[:-5]
        try:
            idx = json.load(io.open(ipath, encoding='utf-8'))
            index_slugs[ch] = {m['slug'] for m in idx['moves']}
        except Exception:
            pass

    low, high, per_move = {}, {}, {}
    builds = set()
    n_files = 0
    for path in sorted(glob.glob(os.path.join(DETAIL_DIR, '*.json'))):
        base = os.path.basename(path)[:-5]
        try:
            ch, slug = base.rsplit('_', 1)
        except ValueError:
            continue
        if slug not in index_slugs.get(ch, set()):
            continue          # 非该角色的招(索引外) — 不入表不报错
        try:
            d = json.load(io.open(path, encoding='utf-8'))
        except Exception as e:
            print('!! %s 损坏(%r) — 跳过' % (base, e))
            continue
        n_files += 1
        builds.add(d.get('build'))
        if 'move' not in d:
            print('!! %s 无move键(%s) — 删' % (
                base, d.get('error', '?')))
            os.remove(path)
            continue
        props = [p.get('id') for p in
                 (d.get('move', {}).get('properties') or [])]
        ids = (SUWAKO_OVERRIDE.get(slug) if ch == 'suwako' else None) \
            or SLUG_IDS.get(slug)
        if ids is None:
            continue
        rec = {'low': 'blockLow' in props, 'high': 'blockHigh' in props}
        per_move.setdefault(ch, {})[slug] = rec
        low.setdefault(ch, [])          # 已测角色即登记(空=实测无下段,
        high.setdefault(ch, [])         #  区别于未测角色的表缺省回落)
        if rec['low']:
            low[ch].extend(ids)
        if rec['high']:
            high[ch].extend(ids)

    for tab in (low, high):
        for ch in tab:
            tab[ch] = sorted(set(tab[ch]))
    # 概览
    print('detail档 %d 个 | api build %s' % (
        n_files, sorted(x for x in builds if x)))
    for ch in sorted(low):
        print('  %-10s low=%s high=%s' % (ch, low[ch], high.get(ch)))
    missing = [ch for ch in
               ('reimu', 'marisa', 'suika') if ch not in low]
    if missing:
        print('!! 主力角色缺low档: %s' % missing)
        sys.exit(1)

    out = {
        'source': 'cleista api v1 detail move.properties '
                  '(blockLow/blockHigh), build %s, 采于2026-10-16'
                  % '/'.join(sorted(x or '?' for x in builds)),
        'slug_ids': {k: v for k, v in SLUG_IDS.items()},
        'note': '必杀5xx无法从招名得知动作ID(docs/soku_action_ids) '
                '不入表(R4空映射优于错映射); f.2A守备与2A同页绑定',
        'low': low,
        'high': high,
        'per_move': per_move,
    }
    io.open(OUT, 'w', encoding='utf8').write(
        json.dumps(out, ensure_ascii=False, indent=1))
    print('→ %s (%d角色)' % (OUT, len(low)))


if __name__ == '__main__':
    main()
