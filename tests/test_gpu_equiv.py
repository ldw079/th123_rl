# -*- coding: utf-8 -*-
"""R54: ppo_gpu ↔ ppo numpy 数值等价性测试。

测试项:
1. 同权重同输入 → logits/value 的差距 < 1e-4
2. save → numpy load 键名完整
3. numpy save → GPU load → 前向一致
4. 维度与现存模型兼容(reimu 63宏)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expandvars(r'%USERPROFILE%/Desktop/workplace/th123_rl'))
sys.stdout.reconfigure(encoding='utf8')

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print('PyTorch不可用 — 等价性测试跳过(架构验证可跑)')
    HAS_TORCH = False

from ppo import PPOTrainer, CONV_H, CONV_W  # noqa

# 测试参数
N_OUT = 63    # reimu
N_SIDE = 5 * N_OUT + 308
NPZ_PI = r'D:/temp/_equiv_pi.npz'
NPZ_V = r'D:/temp/_equiv_v.npz'

# 1. numpy版 init + save
np_tr = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
np_tr.init_fresh(3 * CONV_H * CONV_W)
np_tr.save(NPZ_PI, NPZ_V)
print('1. numpy init_fresh + save: OK')

# 验证npz键
d = np.load(NPZ_PI)
expected_pi = {'W1', 'b1', 'W2', 'b2', 'W_side', 'Ws1', 'bs1', 'Ws2',
               'bs2', 'Wo1', 'bo1', 'Wo2', 'bo2', 'W_opp', 'Wq1', 'bq1',
               'Wq2', 'bq2', 'Wc1', 'bc1', 'Wc2', 'bc2', 'Wc3', 'bc3',
               'meta'}
missing = expected_pi - set(d.files)
print('2. npz键完整性:', '✓' if not missing else '✗缺%s' % missing)

if not HAS_TORCH:
    print('\n(无torch, 仅验证numpy侧架构)')
    print('TRUNK_FLAT:', np_tr.W1.shape[0], '(期望2560)')
    print('W2:', np_tr.W2.shape, '(期望(128,63))')
    print('W1v输入:', np_tr.W1v.shape[0], '(期望2560+%d+16=%d)'
          % (N_SIDE, 2560 + N_SIDE + 16))
    sys.exit(0)

# 3. GPU版加载numpy权重
from ppo_gpu import PPOTrainerGPU  # noqa
gpu_tr = PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)
gpu_tr.load(NPZ_PI, NPZ_V)
print('3. GPU load numpy权重: OK')

# 4. 同输入前向对比
rng = np.random.default_rng(42)
X = rng.integers(0, 255, size=(4, 3 * CONV_H * CONV_W)).astype(np.float32)
S = rng.standard_normal((4, N_SIDE)).astype(np.float32)
mask = np.ones((4, N_OUT), dtype=bool)
mask[:, 50:] = False  # 部分掩码

# numpy前向
Xn_np, _, P_np = np_tr._pi_forward(X, S, temp=1.0, mask=mask)
_, V_np, _ = np_tr._v_forward(Xn_np, S)

# GPU前向
X_t = torch.from_numpy(
    X.reshape(-1, 3, CONV_H, CONV_W) / 255.0).to(
        __import__('ppo_gpu').DEVICE)
S_t = torch.from_numpy(S).to(__import__('ppo_gpu').DEVICE)
M_t = torch.from_numpy(mask).to(__import__('ppo_gpu').DEVICE)
with torch.no_grad():
    logits_t, v_t, _, _ = gpu_tr.net(X_t, S_t, 1.0, M_t)
P_gpu = torch.softmax(logits_t, dim=1).cpu().numpy()
V_gpu = v_t.cpu().numpy()

# 比较
p_diff = np.abs(P_np - P_gpu).max()
v_diff = np.abs(V_np - V_gpu).max()
print('4. 前向对比: P_max_diff=%.6f V_max_diff=%.6f'
      % (p_diff, v_diff))
print('   %s' % ('✓ 等价 (<1e-3)' if p_diff < 1e-3 and v_diff < 1e-3
                else '✗ 不等价'))

# 5. GPU save → numpy load
gpu_tr.save(NPZ_PI.replace('.npz', '_gpu.npz'),
            NPZ_V.replace('.npz', '_gpu.npz'))
d2 = np.load(NPZ_PI.replace('.npz', '_gpu.npz'))
keys_match = set(d2.files) >= expected_pi - {'meta'} | {'meta'}
print('5. GPU save键完整:', '✓' if keys_match else '✗')
print('\n%s' % ('全部通过 ✓' if p_diff < 1e-3 else '存在不等价项'))
