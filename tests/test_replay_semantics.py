# -*- coding: utf-8 -*-
"""R38(第九轮审计P0-4): 经验回放修复的行为测试。

背景: 原实现(a)切片方向反 → 池恒空; (b)回放行未拼mask → 前向广播爆炸
被异步线程吞掉 → 更新静默丢失。本测试用两次连发update驱动真实代码路径:
  1. 第一批: 高优势样本入池(8元组: X/S/A/R/adv/ret/mask/logp_old)
  2. 第二批: 回放行混入 + bc_extra + 2-D bc_mask + B/Q 全对齐, 不抛异常
  3. 池不变量: mask行bool宽N_OUT, logp_old有限, 池容≤500
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.stdout.reconfigure(encoding='utf8')

from ppo import PPOTrainer, CONV_H, CONV_W  # noqa: E402

N_OUT = 4
N_SIDE = 2 * N_OUT + 152 + 75 + 8   # 覆盖对手切片[2*N_OUT+152, +75)
NIN = 3 * CONV_H * CONV_W


def make_batch(rng, n):
    X = rng.integers(0, 255, size=(n, NIN)).astype(np.float32)
    S = rng.standard_normal((n, N_SIDE)).astype(np.float32)
    A = rng.integers(0, N_OUT, size=n).astype(np.int64)
    # 少数大奖励 → 归一化后|adv|>1 → 入池
    R = rng.standard_normal(n).astype(np.float32) * 0.05
    R[:: max(1, n // 6)] = 3.0
    M = rng.random((n, N_OUT)) > 0.3
    M[:, 0] = True    # 每行至少一个合法宏
    Q = rng.integers(0, 8, size=n).astype(np.int64)
    return X, S, A, R, M, Q


def main():
    t = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
    t.init_fresh(NIN)
    rng = np.random.default_rng(42)

    # ---- 第一批: 建池 ----
    X1, S1, A1, R1, M1, Q1 = make_batch(rng, 60)
    t.update([x for x in X1], A1, R1, [s for s in S1], ep_lens=[60],
             ep_terms=[True], masks=M1, opp_next=Q1)
    buf = getattr(t, '_replay_buf', None)
    assert buf is not None, "高优势样本未入池(|adv|>1应存在)"
    assert len(buf) == 8, "池应为8元组(含mask与logp_old)"
    n_pool = len(buf[0])
    assert 0 < n_pool <= 500, "池容量越界: %d" % n_pool
    assert buf[6].dtype == bool and buf[6].shape == (n_pool, N_OUT), \
        "池mask形状/dtype错误: %s %s" % (buf[6].shape, buf[6].dtype)
    assert np.isfinite(buf[7]).all(), "池logp_old含非有限值"
    print("[1] 建池 OK: %d行 mask%s logp_old∈[%.3f,%.3f]" % (
        n_pool, buf[6].shape, buf[7].min(), buf[7].max()))

    # ---- 第二批: 回放混入 + BC-extra + 2-D bc_mask + B/Q ----
    X2, S2, A2, R2, M2, Q2 = make_batch(rng, 40)
    bc_mask = np.ones((40, N_OUT), dtype=np.float32)
    Xe = rng.integers(0, 255, size=(5, NIN)).astype(np.float32)
    Se = rng.standard_normal((5, N_SIDE)).astype(np.float32)
    Ye = rng.integers(0, N_OUT, size=5).astype(np.int64)
    t.update([x for x in X2], A2, R2, [s for s in S2], ep_lens=[40],
             ep_terms=[True], bc_targets=A2, bc_mask=bc_mask,
             masks=M2, opp_next=Q2, bc_extra=(Xe, Se, Ye))
    # 回放行确实被混入: 旧实现pool恒空/形状爆都会在此前炸掉
    n_pool2 = len(t._replay_buf[0])
    print("[2] 回放混入+BC-extra OK, 新池%d行" % n_pool2)

    # ---- 第三批: 池空路径(M全True小批, 无高优势)不受影响 ----
    X3, S3, A3, R3, M3, Q3 = make_batch(rng, 30)
    R3[:] = 0.0   # 无优势 → 不入池, 但旧池仍混入
    t.update([x for x in X3], A3, R3, [s for s in S3], ep_lens=[30],
             ep_terms=[True], masks=M3, opp_next=Q3)
    print("[3] 零优势批 OK")
    print("PASS test_replay_semantics")


if __name__ == '__main__':
    main()
