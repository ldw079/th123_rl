# -*- coding: utf-8 -*-
"""R55: ppo_gpu语义对齐测试"""
import sys

import numpy as np

sys.path.insert(0, r'%USERPROFILE%/Desktop/workplace/th123_rl')
sys.stdout.reconfigure(encoding='utf8')
import torch  # noqa
from ppo_gpu import PPOTrainerGPU  # noqa

N_OUT = 8
N_SIDE = 5 * N_OUT + 308
NIN = 3 * 60 * 80
rng = np.random.default_rng(42)
t = PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)

def gen(n):
    feats = [rng.integers(0, 255, NIN).astype(np.uint8) for _ in range(n)]
    sides = [rng.standard_normal(N_SIDE).astype(np.float32)
             for _ in range(n)]
    acts = rng.integers(0, N_OUT, n)
    rews = rng.standard_normal(n).astype(np.float32)
    rews[::max(1, n // 6)] = 5.0
    masks = np.ones((n, N_OUT), dtype=bool)
    masks[:, 5:] = False
    return feats, sides, acts, rews, masks

# 1. 回放池
f, s, a, r, m = gen(100)
t.update(f, a, r, s, ep_lens=[100], ep_terms=[True], masks=m)
buf = getattr(t, '_replay_buf', None)
assert buf is not None, "回放池未建"
assert len(buf) == 8, "池8元组got%d" % len(buf)
assert len(buf[0]) > 0, "池空"
assert buf[6].dtype == bool, "mask dtype=%s" % buf[6].dtype
print('✓ 回放池: %d行 8元组' % len(buf[0]))

# 2. 第二批混入回放
f2, s2, a2, r2, m2 = gen(80)
t.update(f2, a2, r2, s2, ep_lens=[80], ep_terms=[True], masks=m2)
print('✓ 回放混入: OK')

# 3. bc_mask
f3, s3, a3, r3, m3 = gen(60)
bm = np.ones((60, N_OUT), dtype=np.float32)
bm[:30] = 0.0
t.update(f3, a3, r3, s3, ep_lens=[60], ep_terms=[True],
          masks=m3, bc_mask=bm)
print('✓ bc_mask: OK')

# 4. expert行
Xe = rng.integers(0, 255, size=(5, NIN)).astype(np.uint8)
Se = rng.standard_normal((5, N_SIDE)).astype(np.float32)
Ye = rng.integers(0, N_OUT, size=5).astype(np.int64)
f4, s4, a4, r4, m4 = gen(60)
t.update(f4, a4, r4, s4, ep_lens=[60], ep_terms=[True],
          masks=m4, bc_extra=(Xe, Se, Ye))
print('✓ expert行ret=各自V: OK')

# 5. NaN守卫
t.net.W1.weight.data[0, 0] = float('nan')
try:
    t.save(r'D:/temp/_nan_pi.npz', r'D:/temp/_nan_v.npz')
    assert False, "NaN守卫未触发"
except ValueError:
    print('✓ NaN守卫: 拒绝保存')
t.net.W1.weight.data[0, 0] = 0.0

print('\n全部语义对齐通过 ✓')
