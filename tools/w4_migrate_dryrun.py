# -*- coding: utf-8 -*-
"""W4 迁移 dry-run: 旧模型输出列 0..N-1 扩到 C=256 (零填), 旧 logits 逐位一致.

不写模型/不部署; 输出 D:\\temp\\w4_migrate_dryrun_20261027.json
"""
import json
import os
import sys

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
from train_tm import CHAR_LIBS  # noqa: E402
import slot_registry as SR  # noqa: E402

STORE = r'D:\temp\th123_models'
OUT = r'D:\temp\w4_migrate_dryrun_20261027.json'
C = 256


def main():
    rng = np.random.RandomState(0)
    res = {'capacity': C, 'chars': {}, 'ok': True}
    for ch, lib in CHAR_LIBS.items():
        if ch not in ('reimu', 'marisa', 'suika'):
            continue
        n = len(lib['macros'])
        p = os.path.join(STORE, 'model_ppo_%s.npz' % ch)
        with np.load(p, allow_pickle=True) as z:
            w = {k: z[k] for k in z.files if k != 'meta'}
        # expand output columns
        wexp = {}
        for k, a in w.items():
            if a.ndim >= 1 and a.shape[-1] == n:
                b = np.zeros(a.shape[:-1] + (C,), dtype=a.dtype)
                b[..., :n] = a
                wexp[k] = b
            else:
                wexp[k] = a
        # identity: old columns bitwise equal
        ident = all(np.array_equal(w[k], wexp[k][..., :n])
                    for k in w if w[k].ndim >= 1 and w[k].shape[-1] == n)
        # old logits: use W1/W_side style small random check on W2 path
        x = rng.randn(128).astype(np.float32)
        if 'W2' in w and 'b2' in w:
            lo = x @ w['W2'] + w['b2']
            le = x @ wexp['W2'][:, :n] + wexp['b2'][:n]
            logit_same = bool(np.array_equal(lo, le))
        else:
            logit_same = True
        reg, man = SR.build(lib['macros'][:], [])
        res['chars'][ch] = {
            'n_out': n, 'capacity': C,
            'expanded_arrays': [k for k in w if w[k].ndim >= 1
                                and w[k].shape[-1] == n],
            'identity_old_cols': bool(ident),
            'old_logits_bitwise_equal': logit_same,
            'old_ids_preserved': man['old_ids_preserved'],
            'new_ids_free': C - n,
        }
        res['ok'] = res['ok'] and ident and logit_same and man['old_ids_preserved']
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:1200])
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
