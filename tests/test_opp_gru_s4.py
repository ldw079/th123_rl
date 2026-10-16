# -*- coding: utf-8 -*-
"""S-4预备件行为测试(合并终版方案第二波, flag-off).

cell等价(承test_gru_cell语义)/切片正确性/重放确定性(step==replay)/
系列边界重置/表征投影。合成序列记忆(三拍必跳>75%)属S-4接线批次的
验收, 此处只钉基础语义。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from opp_gru import (gru_cell, gru_slice, OppGRU,     # noqa: E402
                     OPP_GRU_IN, OPP_GRU_H)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    # 1. cell与torch逐位等价(如torch可用)
    try:
        import torch
        import torch.nn as nn
        rng = np.random.default_rng(5)
        g = OppGRU(seed=5)
        x = rng.standard_normal(OPP_GRU_IN).astype(np.float32)
        h0 = rng.standard_normal(OPP_GRU_H).astype(np.float32)
        got = gru_cell(x, h0, g.W_ih, g.W_hh, g.b_ih, g.b_hh)
        cell = nn.GRUCell(OPP_GRU_IN, OPP_GRU_H)
        with torch.no_grad():
            cell.weight_ih.copy_(torch.from_numpy(g.W_ih))
            cell.weight_hh.copy_(torch.from_numpy(g.W_hh))
            cell.bias_ih.copy_(torch.from_numpy(g.b_ih))
            cell.bias_hh.copy_(torch.from_numpy(g.b_hh))
            exp = cell(torch.from_numpy(x).unsqueeze(0),
                       torch.from_numpy(h0).unsqueeze(0))[0].numpy()
        check('cell与torch逐位等价', np.allclose(got, exp, atol=1e-6),
              'max|d|=%.2e' % float(np.abs(got - exp).max()))
    except ImportError:
        check('cell与torch等价(跳过:无torch)', True)

    # 2. 切片: 87=75+12, 取位正确
    N = 70
    side = np.zeros(5 * N + 343, dtype=np.float32)
    b = 2 * N
    side[b + 152:b + 227] = np.arange(75) / 75.0
    side[b + 330:b + 342] = np.arange(12) / 12.0
    side[b + 342] = 0.777          # K5位 — 不得进入GRU输入
    x87 = gru_slice(side, N)
    check('切片87维', x87.shape == (87,))
    check('切片内容', np.allclose(x87[:75], np.arange(75) / 75.0)
          and np.allclose(x87[75:], np.arange(12) / 12.0))
    check('K5位不入GRU', 0.777 not in x87)

    # 3. 重放确定性: 逐步step == 整体replay; 同输入同h
    g2 = OppGRU(seed=9)
    rng = np.random.default_rng(1)
    seq = [rng.standard_normal(5 * N + 343).astype(np.float32)
           for _ in range(20)]
    hs_rep = g2.replay(seq, N)
    h = None
    hs_step = []
    for s in seq:
        h = g2.step(gru_slice(s, N), h)
        hs_step.append(h)
    check('step==replay逐位', all(np.array_equal(a, b)
                                  for a, b in zip(hs_rep, hs_step)))
    hs_rep2 = g2.replay(seq, N)
    check('重放确定性(同种子同参)', all(np.array_equal(a, b)
                                       for a, b in zip(hs_rep, hs_rep2)))

    # 4. 系列边界: h0=None重置; 跨场传值(h携带改变后续h)
    hs_new = g2.replay(seq, N, h0=None)
    check('None起点=零态', np.allclose(hs_new[0], hs_rep[0]))
    h_carry = hs_rep[-1]
    hs_cont = g2.replay(seq[:3], N, h0=h_carry)
    check('跨场传值生效', not np.allclose(hs_cont[0], hs_rep[0]))

    # 5. 表征投影
    r = g2.repr16(hs_rep[-1])
    check('repr16形状与限幅', r.shape == (16,) and (np.abs(r) <= 1).all())

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
