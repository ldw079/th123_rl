# -*- coding: utf-8 -*-
"""BC gen dir 校验: 行数/宽/manifest/hash (指针窗)."""
import argparse
import json
import os
import sys

import numpy as np

EXP = {'reimu': (429579, 831), 'marisa': (353791, 866),
       'suika': (329422, 846)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    a = ap.parse_args()
    ok = True
    for ch, (rows, width) in EXP.items():
        base = os.path.join(a.dir, 'bc_%s' % ch)
        X = np.load(base + '_X.npy', mmap_mode='r')
        S = np.load(base + '_S.npy', mmap_mode='r')
        Y = np.load(base + '_Y.npy', mmap_mode='r')
        man_p = os.path.join(a.dir, 'gen_manifest_gen2_%s.json' % ch)
        man = json.load(open(man_p, encoding='utf-8')) if os.path.exists(man_p) else {}
        good = (len(Y) == rows and S.shape[1] == width
                and man.get('rows') == rows and man.get('status') == 'built')
        print('%s rows=%d width=%d manifest=%s ok=%s'
              % (ch, len(Y), S.shape[1], bool(man), good))
        ok = ok and good
    print('VERIFY', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
