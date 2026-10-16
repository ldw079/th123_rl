# -*- coding: utf-8 -*-
"""JZ-2表库JSON校验与清单."""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = bad = 0
for t in sorted(glob.glob(os.path.join(ROOT, 'data', 'guide_tables',
                                        '*.json'))):
    try:
        json.load(open(t, encoding='utf8'))
        ok += 1
        print('✓', os.path.basename(t))
    except Exception as e:
        bad += 1
        print('✗', os.path.basename(t), str(e)[:70])
print('JZ-2: %d可解析/%d总' % (ok, ok + bad))
sys.exit(1 if bad else 0)
