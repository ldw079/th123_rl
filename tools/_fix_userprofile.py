# -*- coding: utf-8 -*-
"""一次性: P0-2 USERPROFILE字面量修复(从零#5审计).
策略: 在每个受影响文件的头部import os后, 将r'%USERPROFILE%...'路径
统一替换为 os.path.expandvars(r'%USERPROFILE%...') — 确保括号配对.
"""
import io
import os
import re

FILES = [
    'bc_build.py', 'oracle_batch2.py', 'run_parallel.py',
    'tests/test_gpu_equiv.py', 'tests/test_guard_height.py',
    'tools/cleista_ingest.py', 'tools/combo_mine_positional.py',
    'tools/fangyu_extract.py', 'tools/fangyu_index.py',
]


def fix_file(fn):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '..', fn)
    src = io.open(p, encoding='utf8').read()
    lines = src.split('\n')
    fixed = 0
    for i, ln in enumerate(lines):
        if '%USERPROFILE%' not in ln:
            continue
        # Already has expandvars wrapping
        if 'expandvars' in ln:
            continue
        # Pattern: r'%USERPROFILE%\path...' → os.path.expandvars(r'%USERPROFILE%\path...')
        new_ln = re.sub(
            r"(r'[^']*%USERPROFILE%[^']*')",
            r'os.path.expandvars(\1)',
            ln)
        # Pattern: r"%USERPROFILE%\path..." → os.path.expandvars(r"%USERPROFILE%\path...")
        new_ln = re.sub(
            r'(r"[^"]*%USERPROFILE%[^"]*")',
            r'os.path.expandvars(\1)',
            new_ln)
        if new_ln != ln:
            lines[i] = new_ln
            fixed += 1
    if fixed:
        io.open(p, 'w', encoding='utf8').write('\n'.join(lines))
    return fixed


total = 0
for fn in FILES:
    n = fix_file(fn)
    if n:
        print('%s: %d 处' % (fn, n))
        total += n
    else:
        print('%s: 无变化' % fn)
print('\n总计: %d 处' % total)
