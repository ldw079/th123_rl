# -*- coding: utf-8 -*-
"""BC库layout标签迁移(常驻工具: '5N+308:v2'→'5N+316:v2'(标签误写, 宽度本就正确)。
原子重写, 其余字节原样。360对新建tmp实时扫描会瞬时占锁 → replace带重试。"""
import json
import os
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, '.')
from feat_builder import FeatureBuilder  # noqa


def _replace_retry(tmp, dst, tries=6, wait=1.5):
    for i in range(tries):
        try:
            os.replace(tmp, dst)
            return True
        except PermissionError:
            if i == tries - 1:
                return False
            time.sleep(wait)
    return False


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
    w = d['S'].shape[1]
    data = {k: d[k] for k in d.files}
    d.close()   # NpzFile惰性句柄不关=自己锁自己(与训练器持锁同款)
    data['meta'] = np.array(json.dumps(meta))
    tmp = p + '.tmp.npz'
    np.savez(tmp, **data)
    if _replace_retry(tmp, p):
        print('%s: %s → %s (宽%d不变)' % (ch, old, OK, w))
    else:
        print('%s: replace重试耗尽 — 手动检查%s' % (ch, tmp))
