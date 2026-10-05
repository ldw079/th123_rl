# -*- coding: utf-8 -*-
"""高速循环验证: tps=480, 随机输入连打3分钟,
统计: 每局墙钟时长/帧数(含同进程续局成功率)。"""
import random
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from tm_env import TMEnv  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ri():
    return {"H": random.choice([-1, 0, 1]), "A": random.random() < 0.2,
            "B": random.random() < 0.2}


def main():
    env = TMEnv(22300, char_left="reimu", char_right="reimu",
                vs_com=True, tps=480)
    print("tps=480 连续180s...")
    t0 = time.time()
    frames = 0
    ep_frames = 0
    ep_t0 = time.time()
    restarts = 0
    while time.time() - t0 < 180:
        r = env.step(ri(), {})
        if r is None:
            dt = time.time() - ep_t0
            print("局#%d: %d帧 / %.1fs = %.0f帧/s (进程重启%s)"
                  % (env.games, ep_frames, dt, ep_frames / max(dt, 0.1),
                     "是" if "进程重启" in "" else "否"))
            if dt > 4.5:
                restarts += 1
            ep_frames = 0
            ep_t0 = time.time()
            continue
        frames += 1
        ep_frames += 1
    print("总结: %d局 %d帧 平均%.0f帧/s 慢重启(>4.5s)次数=%d"
          % (env.games, frames, frames / 180, restarts))
    env.close()


if __name__ == "__main__":
    main()
