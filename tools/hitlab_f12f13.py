# -*- coding: utf-8 -*-
"""R61-A3(主规划): hitlab裁决F-12/F-13 — 帧级事件检测沿的权威实测。

争议:
  F-13: 防御硬直检测沿现用159-167(错误防御族)。SokuLib文档说150-157
        是正确防御硬直 — 若真, 正确防御(大多数情况)对事件系统不可见;
        R21/XML则称150-153是持防姿态(若真, 纳入150-153会持防时误触发)。
  F-12: 起身事件现用全受击族(50-98+100+143/145) — 站立受击结束也触
        发"起身反应"。真倒地集待实测。

试验矩阵(全部实测dump, 不从先验):
  G1-G4: 攻击高度(5A中/2A下) × 持防姿态(立/蹲) → 防御方action ID分类
  G5:    纯持防不挨打 → 持防姿态是否有独立action ID(R21论断检验)
  H1:    站立受击(5A打木桩) → 站立受击ID族(预期50-58)
  K1/K2: 击倒招(3A扫/2C) → 受击→倒地→起身全ID序列(真倒地集)
"""
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf8")

from soku_client2 import GameEnded  # noqa: E402
from side_driver import EvalEnv  # noqa: E402
from tools.hitlab_probe import (NEUTRAL, ctrl_health, ctrl_pos,  # noqa: E402
                                sync_idle, STRIKE, DUMMY, PORT)


def run_and_collect(env, inp_l_fn, inp_r_fn, frames=110):
    """摆位同步后执行双方脚本, 采集P2(右侧)action轨迹。"""
    lx, rx = 480.0, 480.0 + 70
    synced = sync_idle(env, lx, rx)
    traj = []
    for f in range(frames):
        try:
            r = env.step(inp_l_fn(f) or {}, inp_r_fn(f) or {})
        except Exception:
            break
        if r is None:
            break
        left, right = r[0], r[1]
        traj.append((f, right["action"], right["hp"], right["untech"],
                     right["hitStop"], left["action"]))
    return traj, synced


def runs(seq):
    """(id, 帧数)游程编码。"""
    out = []
    for v in seq:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def show(tag, traj, synced):
    print("\n== %s (synced=%s, %d帧) ==" % (tag, synced, len(traj)))
    acts = runs([t[1] for t in traj])
    # 只打印受击/防御/倒地段(0-300)的游程 + 前8段
    interesting = [(a, n) for a, n in acts if a < 300]
    print("  P2 action游程(<300):", interesting[:14])
    cnt = Counter(t[1] for t in traj)
    print("  P2 ID计数(<300):",
          sorted(((k, v) for k, v in cnt.items() if k < 300)))


def main():
    env = EvalEnv(PORT, char_left="reimu", char_right="reimu",
                  vs_com=False, tps=None)
    print("排干intro...")
    for _ in range(240):
        try:
            if env.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        except Exception:
            break

    results = {}
    trials = [
        ("G1_5A_vs_立防",   STRIKE["5A"](10),      DUMMY["stand_guard"]),
        ("G2_2A_vs_立防",   STRIKE["2A_long"](10), DUMMY["stand_guard"]),
        ("G3_5A_vs_蹲防",   STRIKE["5A"](10),      DUMMY["crouch_guard"]),
        ("G4_2A_vs_蹲防",   STRIKE["2A_long"](10), DUMMY["crouch_guard"]),
        ("G5_纯持防不挨打", lambda f: {},          DUMMY["stand_guard"]),
        ("H1_5A打木桩",     STRIKE["5A"](10),      DUMMY["idle"]),
        ("K1_3A扫击倒",     STRIKE["3A_diag"](10), DUMMY["idle"]),
        ("K2_2C击倒",       STRIKE["2C"](10),      DUMMY["idle"]),
    ]
    for tag, sl, dr in trials:
        for attempt in range(3):
            traj, synced = run_and_collect(env, sl, dr)
            if synced and traj:
                break
            ctrl_health(env.inst, 10000, 10000)
        show(tag, traj, synced)
        results[tag] = [[t[0], t[1], t[2], t[3], t[4], t[5]]
                        for t in traj]

    out = os.path.join(HERE, "hitlab_f12f13.json")
    tmp = out + ".tmp"
    import json
    with open(tmp, "w", encoding="utf8") as fh:
        json.dump({"trials": results,
                   "meta": {"date": time.strftime("%Y-%m-%d %H:%M"),
                            "char": "reimu", "gap": 70}}, fh)
    os.replace(tmp, out)
    print("\n原始dump:", out)
    try:
        env.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
