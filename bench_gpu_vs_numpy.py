# -*- coding: utf-8 -*-
"""R54c: numpy vs torch-CPU PPO更新耗时对比(数据说话)。

当前生产规模(63宏/623侧宽), 典型批大小(700/1000/1500决策),
EPOCHS=1(生产设置)。双实现同参数同数据, 墙钟对比。
"""
import sys
import time

import numpy as np

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
sys.stdout.reconfigure(encoding="utf8")

N_OUT = 63
N_SIDE = 5 * N_OUT + 308
NIN = 3 * 60 * 80  # 14400

# ---- numpy基准 ----
from ppo import PPOTrainer  # noqa: E402

np_tr = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
np_tr.init_fresh(NIN)
np_tr.EPOCHS = 1

# ---- torch基准 ----
import torch  # noqa: E402
from ppo_gpu import PPOTrainerGPU, DEVICE  # noqa: E402
torch.set_num_threads(4)  # 与numpy默认BLAS线程接近

gpu_tr = PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)

rng = np.random.default_rng(42)

def gen_data(n_dec):
    feats = [rng.integers(0, 255, NIN).astype(np.uint8)
             for _ in range(n_dec)]
    sides = [rng.standard_normal(N_SIDE).astype(np.float32)
             for _ in range(n_dec)]
    acts = rng.integers(0, N_OUT, n_dec)
    rews = rng.standard_normal(n_dec).astype(np.float32)
    masks = np.ones((n_dec, N_OUT), dtype=bool)
    masks[:, 40:] = False  # 部分掩码
    return feats, sides, acts, rews, masks

def bench_numpy(feats, sides, acts, rews, masks):
    # 预热
    np_tr.update(feats[:64], acts[:64], rews[:64], sides[:64], [64],
                 masks=masks[:64])
    t0 = time.perf_counter()
    np_tr.update(feats, acts, rews, sides, [len(acts)], masks=masks)
    return time.perf_counter() - t0

def bench_torch(feats, sides, acts, rews, masks):
    # 预热
    gpu_tr.update(feats[:64], acts[:64], rews[:64], sides[:64], [64],
                  masks=masks[:64])
    # 清CUDA缓存(如适用)
    if DEVICE.type == 'cuda':
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    gpu_tr.update(feats, acts, rews, sides, [len(acts)], masks=masks)
    if DEVICE.type == 'cuda':
        torch.cuda.synchronize()
    return time.perf_counter() - t0

print('设备: %s (torch %s, %d线程)' % (
    DEVICE, torch.__version__, torch.get_num_threads()))
print('参数: N_OUT=%d N_SIDE=%d EPOCHS=1 MINIBATCH=64' % (N_OUT, N_SIDE))
print()

results = {}
for n_dec in (700, 1000, 1500):
    feats, sides, acts, rews, masks = gen_data(n_dec)
    # numpy
    np_dt = bench_numpy(feats, sides, acts, rews, masks)
    # torch
    th_dt = bench_torch(feats, sides, acts, rews, masks)
    speedup = np_dt / th_dt if th_dt > 0 else float('inf')
    results[n_dec] = (np_dt, th_dt, speedup)
    print('决策%4d | numpy %6.1fs | torch %6.1fs | 加速比 %.2fx'
          % (n_dec, np_dt, th_dt, speedup))

# 二轮取最优(消除抖动)
print()
print('--- 第二轮(消除抖动) ---')
for n_dec in (700, 1000, 1500):
    feats, sides, acts, rews, masks = gen_data(n_dec)
    np_dt2 = min(bench_numpy(feats, sides, acts, rews, masks),
                 results[n_dec][0])
    th_dt2 = min(bench_torch(feats, sides, acts, rews, masks),
                 results[n_dec][1])
    sp2 = np_dt2 / th_dt2 if th_dt2 > 0 else float('inf')
    print('决策%4d | numpy %6.1fs | torch %6.1fs | 加速比 %.2fx'
          % (n_dec, np_dt2, th_dt2, sp2))

avg_sp = sum(results[n][2] for n in results) / len(results)
print()
print('平均加速比: %.2fx (%s)' % (
    avg_sp,
    'torch-CPU有增益' if avg_sp > 1.15 else
    'torch-CPU无实质增益(需真GPU)' if avg_sp < 0.85 else
    '两者接近(增益不显著)'))
