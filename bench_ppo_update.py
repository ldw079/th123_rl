# -*- coding: utf-8 -*-
"""PPO更新耗时基准(独立运行, 不触碰训练进程):
典型局规模(700/1000/1500决策)的update墙钟, 以及EPOCHS=2对比。"""
import sys
import time

import numpy as np

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from ppo import PPOTrainer  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def bench(n_dec, epochs):
    t = PPOTrainer(n_side=2 * 55 + 64, n_out=55)
    t.init_fresh(14400)
    t.EPOCHS = epochs
    rng = np.random.default_rng(0)
    feats = [rng.integers(0, 255, 14400).astype(np.uint8) for _ in range(n_dec)]
    sides = [rng.standard_normal(2 * 55 + 64).astype(np.float32)
             for _ in range(n_dec)]
    acts = rng.integers(0, 55, n_dec)
    rews = rng.standard_normal(n_dec).astype(np.float32)
    # 预热(首次im2col分配缓存)
    t.update(feats[:64], acts[:64], rews[:64], sides[:64], [64])
    t0 = time.perf_counter()
    t.update(feats, acts, rews, sides, [n_dec])
    return time.perf_counter() - t0


def main():
    for n in (700, 1000, 1500):
        for ep in (4, 2):
            dt = bench(n, ep)
            print("决策%d EPOCHS=%d: %.1fs" % (n, ep, dt))


if __name__ == "__main__":
    main()
