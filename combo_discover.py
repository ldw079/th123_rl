# -*- coding: utf-8 -*-
"""④连段发现管道: 从BC专家数据提取高频宏序列→建议新连段宏。
用法: python combo_discover.py [char] [--min-count 5] [--max-len 4]
输出: 发现的连段模式(按频率排序) + 建议的新宏定义"""
import argparse
import sys
from collections import Counter
from itertools import groupby

import numpy as np

sys.path.insert(0, r'%USERPROFILE%\Desktop\workplace\th123_rl')
sys.stdout.reconfigure(encoding='utf8')


def discover(char, min_count=5, max_len=4):
    bc = np.load(r'data\bc\bc_%s.npz' % char)
    Y = bc['Y'].astype(int)
    # 加载宏名
    if char == 'reimu':
        import macros as M
        names = [m[0] for m in M.MACROS]
    else:
        import importlib
        mod = importlib.import_module('macros_%s' % char)
        names = [m[0] for m in getattr(mod, 'MACROS_%s' % char.upper())]

    # 提取连续不同宏的序列(合并连续同宏)
    seqs = []
    cur = []
    for y in Y:
        mid = int(y)
        if not cur or cur[-1] != mid:
            cur.append(mid)
        if len(cur) > max_len:
            cur.pop(0)
        if len(cur) >= 2:
            seqs.append(tuple(cur))
    # 也提取不合并的原始序列
    raw_seqs = []
    cur = []
    for y in Y:
        mid = int(y)
        if not cur or cur[-1] != mid or len(cur) == 0:
            if cur and len(cur) >= 2:
                raw_seqs.append(tuple(cur))
            cur = [mid]
        else:
            cur.append(mid)
    if cur and len(cur) >= 2:
        raw_seqs.append(tuple(cur))

    # 统计频率
    pairs = Counter()
    triples = Counter()
    for seq in seqs:
        for i in range(len(seq) - 1):
            pairs[seq[i:i+2]] += 1
        for i in range(len(seq) - 2):
            triples[seq[i:i+3]] += 1

    print('=== %s 连段发现(BC %d 决策点) ===' % (char, len(Y)))
    print('\n--- 高频二元组(起手→跟进) ---')
    existing = set()
    for (a, b), cnt in pairs.most_common(30):
        if cnt < min_count:
            break
        na, nb = names[a] if a < len(names) else '?', \
                 names[b] if b < len(names) else '?'
        if na == nb:
            continue
        key = '%s→%s' % (na, nb)
        if key in existing:
            continue
        existing.add(key)
        print('  %4d次  %s → %s' % (cnt, na, nb))

    print('\n--- 高频三元组(起手→连接→终结) ---')
    existing3 = set()
    for (a, b, c), cnt in triples.most_common(20):
        if cnt < min_count:
            break
        na, nb, nc = (names[a] if a < len(names) else '?',
                      names[b] if b < len(names) else '?',
                      names[c] if c < len(names) else '?')
        if na == nb or nb == nc:
            continue
        key = '%s→%s→%s' % (na, nb, nc)
        if key in existing3:
            continue
        existing3.add(key)
        print('  %4d次  %s → %s → %s' % (cnt, na, nb, nc))

    # 建议新宏: 检查高频模式是否已被现有宏覆盖
    print('\n--- 建议(未被现有连段宏覆盖的模式) ---')
    combo_names = set()
    lib = None
    if char == 'reimu':
        import macros as M
        combo_names = M.COMBO_MACROS
    else:
        import importlib
        mod = importlib.import_module('macros_%s' % char)
        combo_names = getattr(mod, 'COMBO_MACROS_%s' % char.upper(), set())

    for (a, b), cnt in pairs.most_common(50):
        if cnt < min_count * 2:
            break
        na, nb = names[a] if a < len(names) else '?', \
                 names[b] if b < len(names) else '?'
        # 检查是否已有连段宏以na开头且包含nb
        covered = False
        for cn in combo_names:
            if cn.startswith(na[:2]) or na in cn:
                covered = True
                break
        if not covered and na != nb:
            print('  建议: ("%s→%s", [...])  %d次' % (na, nb, cnt))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('char', nargs='?', default='reimu')
    ap.add_argument('--min-count', type=int, default=5)
    ap.add_argument('--max-len', type=int, default=4)
    a = ap.parse_args()
    for ch in ([a.char] if a.char != 'all' else ['reimu', 'marisa', 'suika']):
        discover(ch, a.min_count, a.max_len)
        print()
