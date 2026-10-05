# -*- coding: utf-8 -*-
"""VS_PLAYER + 输入表回填验证: TMEnv完整路径(vs_com=False)。
假设: 裸测试没回填0x898680 → 战斗内调度器挂起(13帧停摆)。"""
import random
import sys
import threading
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from tm_env import TMEnv  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ri():
    return {"H": random.choice([-1, 0, 1]), "A": random.random() < 0.15,
            "B": random.random() < 0.15}


def main():
    env = TMEnv(24100, char_left="reimu", char_right="reimu",
                vs_com=False, tps=60)
    print("VS_PLAYER + 回填, PID=%s" % env.pid)
    frames = 0
    t0 = time.time()
    while time.time() - t0 < 120:
        r = env.step(ri(), ri())
        if r is None:
            print("局边界@%d帧(games=%d)" % (frames, env.games))
            frames = 0
            t0 = time.time()
            continue
        frames += 1
        if frames % 300 == 0:
            left, right, weather, objs = r
            print("帧%d: L.hp=%s R.hp=%s obj=%d tbl=%s" % (
                frames, left["hp"], right["hp"], len(objs), env._tbl_filled))
    print("共%d帧 — %s" % (frames,
          "VS_PLAYER稳定运行!" if frames > 1000 else "仍有停摆"))
    env.close()


if __name__ == "__main__":
    main()
