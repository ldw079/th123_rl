# -*- coding: utf-8 -*-
"""BC库layout标签迁移(常驻工具: '5N+308:v2'→'5N+316:v2'(标签误写, 宽度本就正确)。
原子重写, 其余字节原样。"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, '.')
from feat_builder import FeatureBuilder  # noqa

OK = '5N+%d:v2' % FeatureBuilder.CORE_DIMS
for ch in ('reimu', 'marisa', 'suika'):
    p = os.path.join('data', 'bc', 'bc_%s.npz' % ch)
    d = np.load(p, allow_pickle=True)
    meta = json.loads(str(d['meta']))
    if meta.get('layout') == OK:
        print('%s 已是 %s — 跳过' % (ch, OK))
        continue
    old = meta.get('layout')
    meta['layout'] = OK
    data = {k: d[k] for k in d.files}
    data['meta'] = np.array(json.dumps(meta))
    tmp = p + '.tmp.npz'
    np.savez(tmp, **data)
    os.replace(tmp, p)
    print('%s: %s → %s (宽%d不变)'
          % (ch, old, OK, d['S'].shape[1]))
