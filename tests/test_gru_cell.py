# -*- coding: utf-8 -*-
"""E阶段3前置: numpy GRUCell实现 — 行为断言(与torch逐位等价).

方案§5.2: nn.GRUCell(75, 16)的numpy手写版 — 门控求导按本仓库手写
反传惯例, 逐门对账autograd纳入既有等价测试.

W1延迟消融等A/B窗口间隙的前置工作(不触训练栈).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import numpy as np

FAILS = []


def check(name, cond, detail=''):
    print('%-52s %s %s' % (name, 'PASS' if cond else 'FAIL',
                           detail if not cond else ''))
    if not cond:
        FAILS.append(name)


# ---- numpy GRUCell ----
def gru_cell_numpy(x, h_prev, W_ih, W_hh, b_ih, b_hh):
    """手写GRUCell(与torch.nn.GRUCell等价).

    x: (batch, input_dim), h_prev: (batch, hidden_dim)
    W_ih: (3*hidden, input_dim), W_hh: (3*hidden, hidden_dim)
    b_ih/b_hh: (3*hidden,)
    返回h_new: (batch, hidden_dim)
    """
    gi = x @ W_ih.T + b_ih   # (batch, 3*hidden)
    gh = h_prev @ W_hh.T + b_hh
    i_r, i_z, i_n = gi[:, :h_prev.shape[1]], \
        gi[:, h_prev.shape[1]:2*h_prev.shape[1]], \
        gi[:, 2*h_prev.shape[1]:]
    h_r, h_z, h_n = gh[:, :h_prev.shape[1]], \
        gh[:, h_prev.shape[1]:2*h_prev.shape[1]], \
        gh[:, 2*h_prev.shape[1]:]
    r = 1 / (1 + np.exp(-(i_r + h_r)))
    z = 1 / (1 + np.exp(-(i_z + h_z)))
    n = np.tanh(i_n + r * h_n)
    return (1 - z) * n + z * h_prev


# ---- 测试 ----
np.random.seed(42)
IN_DIM, HID_DIM, BATCH = 75, 16, 4

# 随机权重
W_ih = np.random.randn(3 * HID_DIM, IN_DIM).astype(np.float32) * 0.1
W_hh = np.random.randn(3 * HID_DIM, HID_DIM).astype(np.float32) * 0.1
b_ih = np.zeros(3 * HID_DIM, dtype=np.float32)
b_hh = np.zeros(3 * HID_DIM, dtype=np.float32)
x = np.random.randn(BATCH, IN_DIM).astype(np.float32)
h0 = np.zeros((BATCH, HID_DIM), dtype=np.float32)

# 1. 基本前向
h1 = gru_cell_numpy(x, h0, W_ih, W_hh, b_ih, b_hh)
check('前向shape正确', h1.shape == (BATCH, HID_DIM))
check('h0=0时输出非零(门不全关)', np.abs(h1).max() > 1e-6)
check('输出有界(-1,1)', np.all(np.abs(h1) <= 1.0))

# 2. h_prev=0时GRU数学一致性: h_new=(1-z)*tanh(i_n) — z非零故非纯tanh
h1_zero = gru_cell_numpy(x, h0, W_ih, W_hh, b_ih, b_hh)
# 手动计算期望值
gi = x @ W_ih.T + b_ih
gh = h0 @ W_hh.T + b_hh
i_z = gi[:, HID_DIM:2*HID_DIM]
z = 1 / (1 + np.exp(-(i_z + gh[:, HID_DIM:2*HID_DIM])))
i_n = gi[:, 2*HID_DIM:]
expected = (1 - z) * np.tanh(i_n + 0 * gh[:, 2*HID_DIM:])
check('h=0时=(1-z)*tanh(i_n) 数学一致',
      np.abs(h1_zero - expected).max() < 1e-5,
      'diff=%.6f' % np.abs(h1_zero - expected).max())

# 3. 序列展开(5步, 隐状态跨步传递)
hs = [h0]
for t in range(5):
    xt = np.random.randn(BATCH, IN_DIM).astype(np.float32)
    hs.append(gru_cell_numpy(xt, hs[-1], W_ih, W_hh, b_ih, b_hh))
check('5步序列shape不变', hs[-1].shape == (BATCH, HID_DIM))
check('隐状态随时间演化(非恒等)', not np.allclose(hs[1], hs[4]))

# 4. 重置门语义: r→0时**候选n**与h_prev无关(z仍耦合, h_new有z*h_prev项)
# 改测: r→0 AND z→0 → h_new = tanh(i_n), 完全与h_prev无关
b_ih_rz0 = b_ih.copy()
b_ih_rz0[:HID_DIM] = -100       # r→0
b_ih_rz0[HID_DIM:2*HID_DIM] = -100  # z→0
h_test = gru_cell_numpy(x, h0, W_ih, W_hh, b_ih_rz0, b_hh)
h_test_prev = gru_cell_numpy(x, np.ones_like(h0) * 0.5,
                             W_ih, W_hh, b_ih_rz0, b_hh)
check('r→0且z→0时与h_prev解耦',
      np.abs(h_test - h_test_prev).max() < 0.1,
      'diff=%.4f' % np.abs(h_test - h_test_prev).max())

# 5. 更新门语义: z→1时h_new=h_prev(完全保持)
b_ih_z1 = b_ih.copy()
b_ih_z1[HID_DIM:2*HID_DIM] = 100   # z门偏置极大正→sigmoid≈1
h_keep = gru_cell_numpy(x, h0, W_ih, W_hh, b_ih_z1, b_hh)
check('z→1时h_new=h_prev', np.abs(h_keep - h0).max() < 0.01)

# 6. torch等价(如果torch可用)
try:
    import torch
    import torch.nn as nn
    has_torch = True
except ImportError:
    has_torch = False

if has_torch:
    gru = nn.GRUCell(IN_DIM, HID_DIM)
    # 同步权重
    with torch.no_grad():
        gru.weight_ih.copy_(torch.from_numpy(W_ih))
        gru.weight_hh.copy_(torch.from_numpy(W_hh))
        gru.bias_ih.copy_(torch.from_numpy(b_ih))
        gru.bias_hh.copy_(torch.from_numpy(b_hh))
    x_t = torch.from_numpy(x)
    h0_t = torch.from_numpy(h0)
    h1_t = gru(x_t, h0_t).detach().numpy()
    check('numpy↔torch逐位等价(float32)',
          np.abs(h1 - h1_t).max() < 1e-5,
          'max_diff=%.2e' % np.abs(h1 - h1_t).max())

    # 多步等价
    h_np = h0
    h_t = h0_t
    for t in range(10):
        xt = np.random.randn(BATCH, IN_DIM).astype(np.float32)
        h_np = gru_cell_numpy(xt, h_np, W_ih, W_hh, b_ih, b_hh)
        h_t = gru(torch.from_numpy(xt), h_t)
    check('10步序列numpy↔torch等价',
          np.abs(h_np - h_t.detach().numpy()).max() < 1e-4,
          'max_diff=%.2e' % np.abs(h_np - h_t.detach().numpy()).max())
else:
    print('(torch不可用, 跳过等价测试)')

# 7. 合成模式检测(方案§5.3验收前置: "三拍后必跳"模式)
# 构造输入序列: 每第4步注入特征模式, 其余为噪声
pattern = np.ones(IN_DIM, dtype=np.float32)
noise = (np.random.randn(IN_DIM) * 0.1).astype(np.float32)
seq = []
for t in range(40):
    if t % 4 == 3:
        seq.append(pattern + noise * 0.1)
    else:
        seq.append(noise)
h = np.zeros((1, HID_DIM), dtype=np.float32)
hs = []
for xt in seq:
    h = gru_cell_numpy(xt.reshape(1, -1), h, W_ih, W_hh, b_ih, b_hh)
    hs.append(h.copy())
hs = np.vstack(hs)
# GRU应能区分模式帧与噪声帧(隐状态可分)
pattern_states = hs[3::4]
noise_states = np.vstack([hs[i:i+1] for i in range(40) if i % 4 != 3])
sep = np.abs(pattern_states.mean(0) - noise_states.mean(0)).max()
check('合成模式隐状态可分(隔>0.01)', sep > 0.01,
      'separation=%.4f' % sep)

print()
if FAILS:
    print('FAIL(%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('ALL PASS (11)' if has_torch else 'ALL PASS (9)')
