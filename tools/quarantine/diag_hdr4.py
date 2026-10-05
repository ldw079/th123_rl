# -*- coding: utf-8 -*-
"""完整文件名(含比分) x @109-116 对齐。"""
import os

root = r'D:\temp\expert_reps'
shown = 0
for dp, _, fs in os.walk(root):
    for fn in sorted(fs):
        if not fn.lower().endswith('.rep') or shown >= 30:
            continue
        p = os.path.join(dp, fn)
        b = open(p, 'rb').read()
        if len(b) < 121 or b[0] != 0xD2:
            continue
        tail = ' '.join('%02X' % b[i] for i in range(109, 117))
        print('%s | mode=%d | %s' % (fn, b[8], tail))
        shown += 1
