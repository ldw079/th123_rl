# -*- coding: utf-8 -*-
"""R54b: GPU→numpy方向roundtrip测试。

验证: GPU save → numpy ppo.load → numpy前向 == numpy原生前向。
第十七轮发现的断层: GPU save把值头全写pi文件, numpy从v文件读→ValueError。
"""
import sys

import numpy as np

sys.path.insert(0, r'%USERPROFILE%/Desktop/workplace/th123_rl')
sys.stdout.reconfigure(encoding='utf8')

import torch  # noqa
from ppo import PPOTrainer, CONV_H, CONV_W  # noqa
from ppo_gpu import PPOTrainerGPU, DEVICE  # noqa

N_OUT = 63
N_SIDE = 5 * N_OUT + 308
PI1 = r'D:/temp/_rt_np_pi.npz'
V1 = r'D:/temp/_rt_np_v.npz'
PI2 = r'D:/temp/_rt_gpu_pi.npz'
V2 = r'D:/temp/_rt_gpu_v.npz'

# 1. numpy init + save (基准)
np_tr = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
np_tr.init_fresh(3 * CONV_H * CONV_W)
np_tr.save(PI1, V1)
print('1. numpy init+save: OK')

# 2. GPU load numpy → GPU save (转换)
gpu_tr = PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)
gpu_tr.load(PI1, V1)
gpu_tr.save(PI2, V2)
print('2. GPU load→save: OK')

# 3. numpy load GPU save (roundtrip)
np2 = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
np2.load(PI2, V2)
print('3. numpy load GPU save: OK')

# 4. 同输入前向对比
rng = np.random.default_rng(42)
X = rng.integers(0, 255, size=(4, 3 * CONV_H * CONV_W)).astype(np.float32)
S = rng.standard_normal((4, N_SIDE)).astype(np.float32)
mask = np.ones((4, N_OUT), dtype=bool)
mask[:, 50:] = False

# numpy原生前向
Xn, _, P1 = np_tr._pi_forward(X, S, temp=1.0, mask=mask)
_, V1_, _ = np_tr._v_forward(Xn, S)

# roundtrip后前向
Xn2, _, P2 = np2._pi_forward(X, S, temp=1.0, mask=mask)
_, V2_, _ = np2._v_forward(Xn2, S)

p_diff = np.abs(P1 - P2).max()
v_diff = np.abs(V1_ - V2_).max()
print('4. roundtrip对比: P=%.8f V=%.8f' % (p_diff, v_diff))
print('   %s' % ('✓ 双向兼容' if p_diff < 1e-5 and v_diff < 1e-5
                else '✗ 不等价'))
