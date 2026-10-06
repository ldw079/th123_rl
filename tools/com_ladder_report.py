# -*- coding: utf-8 -*-
"""COM难度阶梯读数(用户2026-10-06"记录各模型对应COM难度等级")。

难度档: 0=Easy 1=Normal 2=Hard 3=Lunatic
存档: {STORE}/com_difficulty_{char}{suffix}.json(原子写, 重启续档)。
诊断周期调用: python tools/com_ladder_report.py [--all]
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf8')
STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
NAMES = ('Easy', 'Normal', 'Hard', 'Lunatic')


def read_levels():
    out = {}
    for p in sorted(glob.glob(
            os.path.join(STORE, 'com_difficulty_*.json'))):
        base = os.path.basename(p)[len('com_difficulty_'):-len('.json')]
        try:
            d = json.load(open(p, encoding='utf-8'))
            lv = int(d['difficulty'])
            out[base] = (lv, d.get('ts', '?'))
        except (OSError, ValueError, KeyError):
            out[base] = (None, '损坏')
    return out


def main():
    levels = read_levels()
    if not levels:
        print('无难度存档(全部在Easy起点)')
        return
    print('=== COM难度阶梯读数 ===')
    for name, (lv, ts) in levels.items():
        print('  %-12s %s (存档%s)' % (name,
                                       NAMES[lv] if lv is not None
                                       and 0 <= lv <= 3 else '?%s' % lv, ts))
    return levels


if __name__ == '__main__':
    main()
