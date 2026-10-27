# -*- coding: utf-8 -*-
"""BC gen dir 校验: 行/宽/manifest/hash16 + 真实 loader."""
import argparse
import json
import os
import sys

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
import bc_io  # noqa: E402

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
        meta = json.load(open(base + '_meta.json', encoding='utf-8'))
        hs = meta.get('hashes') or {}
        hash16 = all(isinstance(hs.get(k), str) and len(hs[k]) == 16
                     for k in ('X', 'S', 'Y'))
        if 'I' in hs:
            hash16 = hash16 and len(hs['I']) == 16
        try:
            bx, bs, by = bc_io.load_bank(ch, dirs=[a.dir], verify=True)
            bx2, bs2, by2, bi = bc_io.load_bank_seq(ch, dirs=[a.dir])
            loader_ok = (len(by) == rows and bs.shape[1] == width)
        except Exception as e:
            loader_ok = False
            print(ch, 'loader FAIL', repr(e)[:120])
        man_p = os.path.join(a.dir, 'gen_manifest_gen2_%s.json' % ch)
        man = json.load(open(man_p, encoding='utf-8')) if os.path.exists(man_p) else {}
        good = (len(Y) == rows and S.shape[1] == width and hash16
                and loader_ok and man.get('rows') == rows
                and man.get('status') == 'built')
        print('%s rows=%d width=%d hash16=%s loader=%s manifest=%s ok=%s'
              % (ch, len(Y), S.shape[1], hash16, loader_ok, bool(man), good))
        ok = ok and good
    print('VERIFY', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
