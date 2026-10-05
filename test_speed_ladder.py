# -*- coding: utf-8 -*-
"""倍速阶梯实测: 纯锁步吞吐(无PPO) + 带PPO决策吞吐, 找真实上限。
tps阶梯: 120 → 240 → 480 → 960, 每档30秒。"""
import sys
import time

import numpy as np

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from tm_env import TMEnv  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def measure(env, seconds, ppo=None, mask=None, n_macros=55):
    """锁步循环, 统计帧率与(可选)决策率。"""
    frames = 0
    decisions = 0
    dec_ms = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        if ppo is not None and frames % 12 == 0:
            ts = time.perf_counter()
            # 伪观测(14400随机)+侧 — 只测前向成本
            feat = np.random.randint(0, 255, 14400).astype(np.uint8)
            side = np.zeros(2 * n_macros + 64, dtype=np.float32)
            ppo.sample(feat, side, mask=mask)
            dec_ms.append((time.perf_counter() - ts) * 1000)
            decisions += 1
        r = env.step({}, {})
        if r is None:
            print("  [局终止→重启]")
            continue
        frames += 1
    dt = time.time() - t0
    dm = np.mean(dec_ms) if dec_ms else 0.0
    return frames / dt, decisions / dt, dm


def main():
    from ppo import PPOTrainer
    # 先无PPO纯协议吞吐
    for tps in (120, 240, 480, 960):
        env = TMEnv(21500 + tps, char_left="reimu", char_right="reimu",
                    vs_com=True, tps=tps)
        print("tps=%d 启动..." % tps)
        time.sleep(2)
        fps, dps, _ = measure(env, 20)
        print("  纯锁步: %.0f帧/秒" % fps)
        env.close()
        time.sleep(1)

    # 再带PPO决策成本(单实例, tps=480)
    ppo = PPOTrainer(n_side=2 * 55 + 64, n_out=55)
    ppo.init_fresh(14400)
    mask = np.ones(55, dtype=bool)
    env = TMEnv(21999, char_left="reimu", char_right="reimu",
                vs_com=True, tps=480)
    print("带PPO @tps=480...")
    time.sleep(2)
    fps, dps, dm = measure(env, 20, ppo=ppo, mask=mask)
    print("  带PPO: %.0f帧/秒 决策%.0f/秒 单次采样%.1fms" % (fps, dps, dm))
    env.close()


if __name__ == "__main__":
    main()
