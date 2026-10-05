# -*- coding: utf-8 -*-
"""打印文件名 x @109-116 原始字节, 找语义线索。"""
import os, struct

root = r'D:\temp\expert_reps'
shown = 0
for dp, _, fs in os.walk(root):
    for fn in sorted(fs):
        if not fn.lower().endswith('.rep') or shown >= 25:
            continue
        p = os.path.join(dp, fn)
        b = open(p, 'rb').read()
        if len(b) < 121 or b[0] != 0xD2:
            continue
        tail = ' '.join('%02X' % b[i] for i in range(109, 117))
        print('%-58s mode=%d  @109-116: %s' % (fn[:58], b[8], tail))
        shown += 1
