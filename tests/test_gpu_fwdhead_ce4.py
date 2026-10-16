# -*- coding: utf-8 -*-
"""CE-4: 前向头numpy/GPU双实现等价测试(方案验收判据)。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_fwdhead_equivalence():
    from forward_head import ForwardHead
    from ppo_gpu import PPOTrainerGPU, TRUNK_FLAT
    n_side = 358
    fh = ForwardHead(TRUNK_FLAT, n_side, np.random.default_rng(0))
    g = PPOTrainerGPU(n_side=n_side, n_out=50)
    import torch
    with torch.no_grad():
        g.net.Wf1.weight.copy_(torch.from_numpy(fh.Wf1.T))
        g.net.bf1.copy_(torch.from_numpy(fh.bf1))
        g.net.Wf2.weight.copy_(torch.from_numpy(fh.Wf2.T))
        g.net.bf2.copy_(torch.from_numpy(fh.bf2))
    B = 4
    Xn = np.random.randn(B, TRUNK_FLAT).astype(np.float32)
    S = np.random.randn(B, n_side).astype(np.float32)
    with torch.no_grad():
        inp = torch.cat([torch.from_numpy(Xn), torch.from_numpy(S)], dim=1)
        h = torch.relu(g.net.Wf1(inp) + g.net.bf1)
        gpu_pred = (g.net.Wf2(h) + g.net.bf2).cpu().numpy()
    np_pred, _ = fh.forward(Xn, S)
    diff = np.abs(gpu_pred - np_pred).max()
    assert diff < 1e-5, '不等价! diff=%.2e' % diff


def test_gpu_save_load_fwdhead():
    from ppo_gpu import PPOTrainerGPU
    import tempfile
    g = PPOTrainerGPU(n_side=358, n_out=50)
    import torch
    with torch.no_grad():
        g.net.Wf2.weight[3, 1] = 0.5
    with tempfile.TemporaryDirectory() as td:
        import os
        p1 = os.path.join(td, 'a.npz')
        p2 = os.path.join(td, 'a_v.npz')
        g.save(p1, p2)
        g2 = PPOTrainerGPU(n_side=358, n_out=50)
        g2.load(p1, p2)
        assert abs(g2.net.Wf2.weight[3, 1].item() - 0.5) < 1e-6


if __name__ == '__main__':
    for fn in [test_fwdhead_equivalence, test_gpu_save_load_fwdhead]:
        fn()
        print('✓', fn.__name__)
    print('test_gpu_fwdhead_ce4: 全部通过')
