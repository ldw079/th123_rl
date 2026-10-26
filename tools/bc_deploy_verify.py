# -*- coding: utf-8 -*-
"""BC deploy verify: 行数/宽度/meta hash/加载（部署窗用）."""
import json
import sys

import numpy as np

STORE = r'D:\temp\th123_models'
EXP = {'reimu': (429579, 831), 'marisa': (353791, 866),
       'suika': (329422, 846)}


def main():
    ok = True
    out = {}
    for ch, (rows, width) in EXP.items():
        X = np.load('%s/bc_%s_X.npy' % (STORE, ch), mmap_mode='r')
        S = np.load('%s/bc_%s_S.npy' % (STORE, ch), mmap_mode='r')
        Y = np.load('%s/bc_%s_Y.npy' % (STORE, ch), mmap_mode='r')
        meta = json.load(open('%s/bc_%s_meta.json' % (STORE, ch),
                              encoding='utf-8'))
        r = {'rows': int(len(Y)), 'rows_ok': int(len(Y)) == rows,
             'X_width': int(X.shape[1]), 'S_width': int(S.shape[1]),
             'width_ok': int(S.shape[1]) == width,
             'meta_rows_ok': int(meta.get('rows', -1)) == len(Y)}
        r['ok'] = r['rows_ok'] and r['width_ok'] and r['meta_rows_ok']
        ok = ok and r['ok']
        out[ch] = r
    print(json.dumps({'ok': ok, 'chars': out}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
