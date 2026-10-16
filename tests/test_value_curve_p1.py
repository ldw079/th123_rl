# -*- coding: utf-8 -*-
"""P1-8(从零#4): W4价值曲线2D未reshape回归测试 —
自上线即死(114/147次异常恒空)的配对断言: 输入必须转4D再喂conv网。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import numpy as np


def test_reshape_4d_and_trajectory():
    import value_curve as vc

    class MockNet:
        def __init__(self):
            self.got = None

        def __call__(self, X, S):
            self.got = tuple(X.shape)
            n = X.shape[0]
            import torch
            return (torch.zeros(n, 10), torch.full((n,), 0.5), None)

    arr = {'feats': np.random.randint(0, 256, (300, 14400), dtype=np.uint8),
           'sides': np.random.rand(300, 693).astype(np.float32)}
    net = MockNet()
    traj = vc.episode_values(net, arr, every=30)
    assert net.got is not None and net.got[1:] == (3, 60, 80), \
        'conv输入非4D: %r (P1-8回归 — 2D直喂每批RuntimeError)' % (net.got,)
    assert len(traj) == 10 and all(abs(v - 0.5) < 1e-6 for _f, v in traj)
    e, m, l = vc.thirds_mean(traj)
    assert abs(e - 0.5) < 1e-6 and abs(l - 0.5) < 1e-6


def test_value_line_summary():
    import value_curve as vc
    line = vc.value_line([([(0, 1.0), (30, 0.8)], 'W'),
                          ([(0, 0.2)], 'L'), (None, 'W')])
    assert 'W局均值0.900(n1)' in line and 'L局均值0.200(n1)' in line


if __name__ == '__main__':
    for fn in [test_reshape_4d_and_trajectory, test_value_line_summary]:
        fn()
        print('✓', fn.__name__)
    print('test_value_curve_p1: 全部通过')
