# -*- coding: utf-8 -*-
"""最终配置基准: conv 16/32/32 + ACCUM_EP=1 + EPOCHS=1 + BC + 全部改进。"""
import sys, time
import numpy as np
sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, r'%USERPROFILE%\Desktop\workplace\th123_rl')
import ppo

print('TRUNK_FLAT=%d CONV=%d/%d/%d EPOCHS=%d' % (
    ppo.TRUNK_FLAT, ppo.CONV1_F, ppo.CONV2_F, ppo.CONV3_F,
    ppo.PPOTrainer.EPOCHS))

tr = ppo.PPOTrainer(n_side=2 * 55 + 331, n_out=55)
tr.init_fresh(ppo.TRUNK_FLAT)
rng = np.random.default_rng(1)

# 单局规模(ACCUM_EP=1): ~800决策
N = 800
X = rng.integers(0, 255, (N, 14400), dtype=np.uint8)
S = rng.standard_normal((N, 2 * 55 + 331)).astype(np.float32)
A = rng.integers(0, 55, N)
R = rng.standard_normal(N).astype(np.float32)
bc_X = rng.integers(0, 255, (64, 14400), dtype=np.uint8)
bc_S = rng.standard_normal((64, 2 * 55 + 331)).astype(np.float32)
bc_Y = rng.integers(0, 55, 64)

t0 = time.time()
st = tr.update(list(X), list(A), list(R), list(S), [N],
               ep_terms=[True], bc_extra=(bc_X, bc_S, bc_Y))
dt = time.time() - t0
print('\n单局(800样本)×1epoch含BC: %.1f秒' % dt)
print('值损: %.2f KL: %.4f' % (st['value_loss'], st['kl']))
updates_hr = 3600 / max(dt + 240, 240)  # 更新时间+采集时间(~4分钟/局)
print('估算更新/小时: %.0f (采集~4分钟/局)' % updates_hr)
print('学习吞吐: %.0f 决策/小时' % (updates_hr * N))
