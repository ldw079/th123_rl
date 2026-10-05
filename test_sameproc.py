# -*- coding: utf-8 -*-
"""同进程续局修复验证: mod等场景稳定+键管理器重置后, 连续多局不停进程。"""
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
    return {"H": random.choice([-1, 0, 1]), "A": random.random() < 0.15,
            "B": random.random() < 0.1, "C": random.random() < 0.03}


def main():
    env = TMEnv(25500, char_left="reimu", char_right="reimu",
                vs_com=True, tps=240)
    t0 = time.time()
    frames = 0
    proc_restarts = 0
    while time.time() - t0 < 180:
        r = env.step(ri(), {})
        if r is None:
            dt = time.time() - t0
            gap = time.time() - main_last_ep if hasattr(main, 'last_ep') else 0
            # 检测是否进程重启(新PID = 进程重启)
            is_restart = env.pid != main_last_pid if hasattr(main, 'last_pid') else False
            tag = "进程重启" if env.inst.proc.pid != main_last_pid else "同进程续局"
            print("[%5.1fs] 局#%d 结束 (%s)" % (dt, env.games, tag))
            main_last_pid = env.inst.proc.pid
            main_last_ep = time.time()
            frames = 0
            continue
        frames += 1
        main_last_pid = env.inst.proc.pid
    print("180s测试完成: %d局" % env.games)
    env.close()


if __name__ == "__main__":
    main()
