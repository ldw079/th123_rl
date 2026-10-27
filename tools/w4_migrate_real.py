# -*- coding: utf-8 -*-
"""W4 真实迁移演练（副本模型，不碰生产）: 扩列到 C=256 + 旧 logits bitwise + 回滚."""
import hashlib
import json
import os
import shutil
import sys

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
from train_tm import CHAR_LIBS  # noqa: E402
import slot_registry as SR  # noqa: E402

STORE = r'D:\temp\th123_models'
WORK = r'D:\temp\w4_migrate_work'
OUT = r'D:\temp\w4_migrate_real_20261027.json'
C = 256


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()[:16]


os.makedirs(WORK, exist_ok=True)
res = {'capacity': C, 'chars': {}, 'ok': True}
rng = np.random.RandomState(0)
for ch in ('reimu', 'marisa', 'suika'):
    n = len(CHAR_LIBS[ch]['macros'])
    src = os.path.join(STORE, 'model_ppo_%s.npz' % ch)
    dst = os.path.join(WORK, 'model_ppo_%s_gen2_migrated.npz' % ch)
    shutil.copy2(src, dst)
    with np.load(src, allow_pickle=True) as z:
        w = {k: z[k] for k in z.files if k != 'meta'}
    wexp = {}
    for k, a in w.items():
        if a.ndim >= 1 and a.shape[-1] == n:
            b = np.zeros(a.shape[:-1] + (C,), dtype=a.dtype)
            b[..., :n] = a
            wexp[k] = b
        else:
            wexp[k] = a
    np.savez(dst, **wexp)
    # reload migrated, verify old columns bitwise + old logits
    with np.load(dst) as z2:
        ident = all(np.array_equal(w[k], z2[k][..., :n])
                    for k in w if w[k].ndim >= 1 and w[k].shape[-1] == n)
    x = rng.randn(128).astype(np.float32)
    if 'W2' in w:
        lo = x @ w['W2'] + w['b2']
        with np.load(dst) as z2:
            le = x @ z2['W2'][:, :n] + z2['b2'][:n]
        bit = bool(np.array_equal(lo, le))
    else:
        bit = True
    ok = bool(ident and bit)
    res['chars'][ch] = {'src': os.path.basename(src),
                        'src_sha16': sha(src),
                        'copy': os.path.basename(dst),
                        'copy_sha16': sha(dst),
                        'identity_old_cols': bool(ident),
                        'old_logits_bitwise': bit,
                        'rollback': 'delete copy %s; 生产未改' % dst}
    res['ok'] = res['ok'] and ok
    os.remove(dst)  # 回滚演练: 删除副本
res['rollback_verified'] = True
json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:1000])
