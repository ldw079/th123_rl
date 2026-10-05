# -*- coding: utf-8 -*-
"""R60-A5(主规划): learner机型基准 — numpy vs torch-CPU × 批档(1k/4k/8k/16k)。

目的: fleet learner批规模4-8k(上限16k重批)下, 决定云实例选型
(CPU实例 vs GPU实例 — 差价约一倍)。判定输入:
- 若torch-CPU在8k档update <10s(numpy <60s): CPU实例可承担learner
  (GPU实例仅在16actor满配时必要);
- 外推: 云vCPU单核性能按本机0.7-1.0折算。
独立运行, 不触碰训练进程。"""
import sys
import time

import numpy as np

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")

try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

N_OUT = 55
N_SIDE = 5 * N_OUT + 308


def synth(n, rng):
    return (rng.integers(0, 255, (n, 14400)).astype(np.uint8),
            rng.standard_normal((n, N_SIDE)).astype(np.float32),
            rng.integers(0, N_OUT, n).astype(np.int64),
            rng.standard_normal(n).astype(np.float32),
            (rng.random((n, N_OUT)) > 0.15))


def main():
    from ppo import PPOTrainer
    t_np = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
    t_np.init_fresh(14400)
    rng = np.random.default_rng(0)
    print("%6s %10s %10s %8s" % ("决策", "numpy(s)", "torchCPU", "加速比"))
    torch_tr = None
    for n in (1000, 4000, 8000, 16000):
        X, S, A, R, M = synth(n, rng)
        # 预热(首跑分配缓存)
        t_np.update(X[:64], A[:64], R[:64], S[:64], [64], masks=M[:64])
        t0 = time.perf_counter()
        t_np.update(X, A, R, S, [n], masks=M)
        dt_np = time.perf_counter() - t0
        dt_tc = float('nan')
        try:
            if torch_tr is None:
                from ppo_gpu import PPOTrainerGPU
                import tempfile
                import os
                torch_tr = PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)
                tmp = tempfile.mkdtemp()
                pi, vv = os.path.join(tmp, 'b.npz'), os.path.join(tmp, 'b_v.npz')
                t_np.save(pi, vv)
                torch_tr.load(pi, vv)
                torch_tr.update(X[:64], A[:64], R[:64], S[:64], [64],
                                masks=M[:64])
            t0 = time.perf_counter()
            torch_tr.update(X, A, R, S, [n], masks=M)
            dt_tc = time.perf_counter() - t0
        except Exception as e:
            print("  torch档%d异常: %s" % (n, e))
        print("%6d %10.1f %10s %8s" % (
            n, dt_np,
            ('%.1f' % dt_tc) if dt_tc == dt_tc else '-',
            ('%.1fx' % (dt_np / dt_tc)) if dt_tc == dt_tc else '-'))
    print("\n判定输入(云vCPU按本机0.7-1.0折算): 见上表 → 决策记录入METHODOLOGY")


if __name__ == "__main__":
    main()
