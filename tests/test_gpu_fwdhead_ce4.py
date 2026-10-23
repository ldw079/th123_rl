# -*- coding: utf-8 -*-
"""Gen-1(2026-10-20): Wf1/Wf2 死重移除回归测试(替代原 CE-4 GPU 前向头等价测试).

Wf1/Wf2 从未进 loss/forward 决策(死重 108k 参数) → Gen-1 删除:
1) net 不再有 Wf1/bf1/Wf2/bf2 参数;
2) forward 仍返回 4 元组, 第4项 fwd_pred=零(旧调用方兼容);
3) 旧档(含 Wf 键)仍可 load — 未知键忽略.
"""
import os
import sys

import torch

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
os.chdir(WT)
os.environ['TH123_MEM_DECISIONS'] = '0'
import ppo_gpu as G  # noqa: E402
from feat_builder import FeatureBuilder  # noqa: E402

PI = r'D:\temp\th123_models\model_ppo_reimu_fleet.npz'
VV = r'D:\temp\th123_models\model_ppo_reimu_fleet_v.npz'
N_OUT = 88
N_SIDE = 5 * N_OUT + FeatureBuilder.CORE_DIMS  # task-50: 双宽(GEN2=391)

tr = G.PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)
net = tr.net
names = {n for n, _ in net.named_parameters()}
print('== Gen-1 Wf removal ==')
assert 'Wf1.weight' not in names and 'bf1' not in names, 'Wf1 残留'
assert 'Wf2.weight' not in names and 'bf2' not in names, 'Wf2 残留'
print('  PASS  net 无 Wf1/Wf2 参数')

tr.load(PI, VV)     # 旧档含 Wf 键 → 必须被忽略
print('  PASS  旧档(含Wf键)可载')

x = torch.zeros(2, 3, 60, 80)
S = torch.zeros(2, N_SIDE)
with torch.no_grad():
    out = net(x, S, tr._temp, None)
assert len(out) == 4, 'forward 返回元组数变化'
assert out[3].shape == (2, 4) and float(out[3].abs().max()) == 0.0
print('  PASS  forward 4元组 + fwd_pred=零(兼容)')
print('==== Gen-1 Wf removal: 3 PASS / 0 FAIL ====')
