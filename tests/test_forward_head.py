# -*- coding: utf-8 -*-
"""CE-4 前向头单元测试 — numpy版前向/梯度/目标提取。

不测接线(未接线); 只测数值正确性(损失、梯度、形状)。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from forward_head import ForwardHead, FWD_DIMS, FWD_HIDDEN, fwd_targets


def test_shapes():
    trunk, n_side = 128, 358
    fh = ForwardHead(trunk, n_side, np.random.default_rng(0))
    Xn = np.random.randn(4, trunk).astype(np.float32)
    S = np.random.randn(4, n_side).astype(np.float32)
    pred, h = fh.forward(Xn, S)
    assert pred.shape == (4, FWD_DIMS)
    assert h.shape == (4, FWD_HIDDEN)
    assert fh.Wf1.shape == (trunk + n_side, FWD_HIDDEN)
    assert fh.Wf2.shape == (FWD_HIDDEN, FWD_DIMS)


def test_zero_init_pred():
    """小初始化Wf2 → 初始预测接近0(不干扰主策略)。"""
    trunk, n_side = 64, 100
    fh = ForwardHead(trunk, n_side, np.random.default_rng(1))
    Xn = np.random.randn(2, trunk).astype(np.float32)
    S = np.random.randn(2, n_side).astype(np.float32)
    pred, _ = fh.forward(Xn, S)
    assert np.abs(pred).max() < 0.5   # 小初始化


def test_loss_and_grads():
    """损失>0; 梯度形状正确; 数值梯度一致性。"""
    trunk, n_side = 32, 50
    fh = ForwardHead(trunk, n_side, np.random.default_rng(2))
    B = 8
    Xn = np.random.randn(B, trunk).astype(np.float32)
    S = np.random.randn(B, n_side).astype(np.float32)
    tgt = np.random.rand(B, FWD_DIMS).astype(np.float32)

    loss, dXn, dS, grads = fh.loss_and_grads(Xn, S, tgt)
    assert loss > 0
    assert dXn.shape == (B, trunk)
    assert dS.shape == (B, n_side)
    assert grads['Wf1'].shape == fh.Wf1.shape
    assert grads['Wf2'].shape == fh.Wf2.shape

    # 数值梯度检查(对一个Wf2元素)
    eps = 1e-4
    orig = fh.Wf2[0, 0].copy()
    fh.Wf2[0, 0] = orig + eps
    loss_p, _, _, _ = fh.loss_and_grads(Xn, S, tgt)
    fh.Wf2[0, 0] = orig - eps
    loss_m, _, _, _ = fh.loss_and_grads(Xn, S, tgt)
    fh.Wf2[0, 0] = orig
    num_grad = (loss_p - loss_m) / (2 * eps)
    ana_grad = grads['Wf2'][0, 0]
    assert abs(num_grad - ana_grad) < 1e-3, \
        '数值梯度%.6f vs 解析%.6f' % (num_grad, ana_grad)


def test_fwd_targets():
    """目标提取: **真实FeatureBuilder产出**上验证(R138 — 原fictional
    core索引通过=假绿, 与R133 trunk=128同型错误)。"""
    from feat_builder import FeatureBuilder
    W = {'id': 0, 'active': 0, 'displayed': None}

    def build_core(ox, oxx, air=False):
        fb = FeatureBuilder(88)
        base = {'spirit': 1000, 'position.y': 50.0, 'hp': 10000,
                'action': 0, 'cardGauge': 0, 'score': 0,
                'hand': b'\xff' * 10, 'comboDamage': 0, 'untech': 0,
                'airBorne': False, 'timeStop': 0, 'hitStop': 0,
                'guardCount': 0}
        l = dict(base); l['position.x'] = float(ox)
        l['direction'] = 1; l['airBorne'] = air
        r = dict(base); r['position.x'] = float(oxx)
        return np.asarray(fb.build(l, r, W, []),
                          dtype=np.float32)[:358]

    # 双方贴角同位+滞空
    tgt = fwd_targets(build_core(100, 100, air=True))
    assert tgt.shape == (4,)
    assert tgt[0] == 0.0                      # adx=0(同位)
    assert tgt[1] == 1.0                      # own贴角([150]=1.5→1)
    assert tgt[2] == 1.0                      # opp贴角
    assert tgt[3] == 1.0                      # air

    # own版中 opp右角 地面
    tgt2 = fwd_targets(build_core(640, 1200))
    assert tgt2[1] == 0.0                     # own不在角
    assert tgt2[2] == 1.0                     # opp在角(1200>1120)
    assert abs(tgt2[0] - 560.0 / 600.0) < 1e-5  # adx=560(/600口径)
    assert tgt2[3] == 0.0                     # 地面

    # adx线性(段1标量[4]的clip(adx/600))
    t3 = fwd_targets(build_core(640, 340))    # adx=300
    assert abs(t3[0] - 0.5) < 1e-5

    # 右角对称性: own右角也触发(>1120)
    tgt4 = fwd_targets(build_core(1180, 640))
    assert tgt4[1] == 1.0 and tgt4[2] == 0.0


def test_learning_convergence():
    """简单学习任务: 100步梯度下降后损失显著下降。"""
    trunk, n_side = 16, 20
    fh = ForwardHead(trunk, n_side, np.random.default_rng(3))
    B = 32
    Xn = np.random.randn(B, trunk).astype(np.float32)
    S = np.random.randn(B, n_side).astype(np.float32)
    tgt = np.random.rand(B, FWD_DIMS).astype(np.float32)
    lr = 5e-3
    losses = []
    for step in range(100):
        loss, _, _, grads = fh.loss_and_grads(Xn, S, tgt)
        losses.append(loss)
        fh.Wf1 -= lr * grads['Wf1']
        fh.bf1 -= lr * grads['bf1']
        fh.Wf2 -= lr * grads['Wf2']
        fh.bf2 -= lr * grads['bf2']
    assert losses[-1] < losses[0] * 0.5, \
        '100步后损失未减半: %.4f → %.4f' % (losses[0], losses[-1])


if __name__ == '__main__':
    for fn in [test_shapes, test_zero_init_pred, test_loss_and_grads,
               test_fwd_targets, test_learning_convergence]:
        fn()
        print('✓', fn.__name__)
    print('test_forward_head: 全部通过')
