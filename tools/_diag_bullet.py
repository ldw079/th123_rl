# -*- coding: utf-8 -*-
"""弹幕标注诊断: TR shard原始ilog里A/B/C/D键按压率.

位码(input_codec实证): bit4=A bit5=B bit6=C bit7=D, bit8=AandB→SC。
首版曾错用0x80/0x100(实为D/SC) — "B键6-30%"实为D键(飞翔)。
"""
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
shards = sorted(glob.glob(os.path.join(
    ROOT, 'data', 'oracle_v2', 'shards', 'tr0000*.npz')))[:8]
BIT_A, BIT_B, BIT_C, BIT_D = 0x10, 0x20, 0x40, 0x80
for sp in shards:
    d = np.load(sp, allow_pickle=True)
    if 'ilog' not in d.files:
        print(os.path.basename(sp), '无ilog')
        continue
    arr = d['ilog']
    if arr.ndim != 2 or arr.shape[1] != 4:
        print(os.path.basename(sp), 'ilog形状', arr.shape)
        continue
    li, ri = arr[:, 0].astype(np.uint16), arr[:, 2].astype(np.uint16)
    meta = json.loads(str(d['meta']))
    for side, u in (('L', li), ('R', ri)):
        pa = ((u & BIT_A) != 0).mean() * 100
        pb = ((u & BIT_B) != 0).mean() * 100
        pc = ((u & BIT_C) != 0).mean() * 100
        pd = ((u & BIT_D) != 0).mean() * 100
        print('%-24s %s %-16s A%5.2f%% B%5.2f%% C%5.2f%% D%5.2f%%' % (
            os.path.basename(sp), side, str(meta.get('chars', '?')),
            pa, pb, pc, pd))
