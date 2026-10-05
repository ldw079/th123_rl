# -*- coding: utf-8 -*-
"""验证假设: @113/@114 == 输入流偶/奇位置非零条目计数?"""
import os, struct

root = r'D:\temp\expert_reps'
shown = 0
match_cnt = 0
total = 0
for dp, _, fs in os.walk(root):
    for fn in sorted(fs):
        if not fn.lower().endswith('.rep') or shown >= 60:
            continue
        p = os.path.join(dp, fn)
        b = open(p, 'rb').read()
        if len(b) < 123 or b[0] != 0xD2:
            continue
        n_entries = (len(b) - 121) // 2
        inputs = struct.unpack_from('<%dH' % n_entries, b, 121)
        nz_even = sum(1 for i in range(0, n_entries, 2) if inputs[i] != 0)
        nz_odd = sum(1 for i in range(1, n_entries, 2) if inputs[i] != 0)
        n_runs_even = 0  # 偶位置上"与前一条不同"的次数
        n_runs_odd = 0
        prev_e = prev_o = None
        for i in range(0, n_entries, 2):
            if inputs[i] != prev_e:
                n_runs_even += 1
                prev_e = inputs[i]
        for i in range(1, n_entries, 2):
            if inputs[i] != prev_o:
                n_runs_odd += 1
                prev_o = inputs[i]
        print('%-30s @113/114=%02X/%02X  nz=%d/%d  runs=%d/%d' % (
            fn[:30], b[113], b[114], nz_even, nz_odd, n_runs_even, n_runs_odd))
        if (b[113], b[114]) == (nz_even, nz_odd) or \
           (b[113], b[114]) == (nz_odd, nz_even):
            match_cnt += 1
        if (b[113], b[114]) == (n_runs_even, n_runs_odd) or \
           (b[113], b[114]) == (n_runs_odd, n_runs_even):
            match_cnt += 100
        total += 1
        shown += 1
print('\nnz匹配: %d/100权重, runs匹配: %d (共%d文件)' % (match_cnt % 100, match_cnt // 100, total))
