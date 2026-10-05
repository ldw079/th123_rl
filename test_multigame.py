# -*- coding: utf-8 -*-
"""多环压力测试: VS_PLAYER双控 + 连续多局自动续局(按局重启) + 随机走位/出招。"""
import random
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from tm_env import TMEnv  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rand_input():
    return {
        "H": random.choice([-1, 0, 1]),
        "V": random.choice([-1, 0, 1]),
        "A": random.random() < 0.15,
        "B": random.random() < 0.2,
        "C": random.random() < 0.05,
        "D": random.random() < 0.05,
    }


def main():
    env = TMEnv(20800, char_left="reimu", char_right="reimu",
                vs_com=True, tps=120)
    print("PID=%s VS_COM开局OK, tps=120(2倍速), 连续跑1分钟..." % env.pid)
    frames = 0
    t0 = time.time()
    last_report = t0
    while time.time() - t0 < 60:
        r = env.step(rand_input(), rand_input())
        if r is None:
            continue
        left, right, weather, objs = r
        frames += 1
        if time.time() - last_report > 10:
            print("[%5.1fs] 局#%d 帧%d L.hp=%s R.hp=%s obj=%d"
                  % (time.time() - t0, env.games, frames, left["hp"],
                     right["hp"], len(objs)))
            last_report = time.time()
    print("总结: %d局 %d帧" % (env.games, frames))
    env.close()


if __name__ == "__main__":
    main()
