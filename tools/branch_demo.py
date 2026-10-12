# -*- coding: utf-8 -*-
"""R61m(E1): 分支演示杠杆 — "同一局面 N 种应对后果对比"演示器。

利用mod的SET_POSITION/SET_HEALTH/SET_WEATHER操作(scenario_b设计
称"全项目最被低估资产"), 在确定性锁步下:
1. 设定一个游戏局面(位置/血量/天气/角色)
2. 对同一局面分别执行N种不同应对(策略采样或指定宏)
3. 记录每种应对的后果(伤害/承伤/回合结束)
4. 输出对比报告(教学层的数据基础)

用法: python tools/branch_demo.py [--char reimu] [--scenarios 3]
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

from soku_client2 import (GameEnded, OPCODE_SET_HEALTH,  # noqa: E402
                           OPCODE_SET_POSITION)
from side_driver import EvalEnv  # noqa: E402

# G2(R77): 端口单一事实源(portmap.RESERVED) — 原字面量20935注释
# "eval段"已漂移(实际hitlab段); opcode同收编soku_client2
from portmap import reserved_port
PORT = reserved_port("branch_demo")
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
OP_SET_HEALTH = OPCODE_SET_HEALTH
OP_SET_POSITION = OPCODE_SET_POSITION

# 标准局面模板(教学场景)
SCENARIOS = {
    # 场景A: 中距对峙(对手即将出招) — 教"防还是插"
    "mid_range": {
        "desc": "中距对峙(400px) — 防御/前冲/插动三分支",
        "pos": (480.0, 0.0, 880.0, 0.0),   # P1/P2位置
        "hp": (10000, 10000),
        "gap": 400,
    },
    # 场景B: 被压起身 — 教"起身选择"
    "wakeup": {
        "desc": "被压起身(近距200px) — 起身穿/防/反三分支",
        "pos": (500.0, 0.0, 700.0, 0.0),
        "hp": (8000, 10000),   # 自身残血
        "gap": 200,
    },
    # 场景C: 版边被压制 — 教"逃压手段"
    "corner_pressure": {
        "desc": "版边被压(近距150px) — 结界/投技/防三分支",
        "pos": (80.0, 0.0, 230.0, 0.0),
        "hp": (6000, 10000),
        "gap": 150,
    },
}


def ctrl_health(inst, l, r):
    inst._send(struct.pack("<BHH", OP_SET_HEALTH, l, r))


def ctrl_pos(inst, lx, ly, rx, ry):
    inst._send(struct.pack("<B4f", OP_SET_POSITION, lx, ly, rx, ry))


def setup_scenario(env, scen):
    """设定局面并等待稳定。"""
    lx, ly, rx, ry = scen["pos"]
    ctrl_health(env.inst, scen["hp"][0], scen["hp"][1])
    ctrl_pos(env.inst, lx, ly, rx, ry)
    for _ in range(60):
        try:
            env.step(dict(NEUTRAL), dict(NEUTRAL))
        except Exception:
            return False
    return True


def run_branch(env, scen, macro_script, frames=120, opp_driver=None):
    """一种应对分支: 设定局面→执行宏→采集后果。
    E1-v2(2026-10-07): opp_driver提供时对手为模型驱动(真教学 — 挂机
    对手只演示可达性, 会反抗的对手才演示"应对的代价与收益")。"""
    setup_scenario(env, scen)
    traj = []
    my_hp0, opp_hp0 = None, None
    opp_inp = {}
    for f in range(frames):
        # P0-C(从零#2): 原对macro_script(闭包函数)取len()→首帧TypeError
        # 进程即死 — mk_input已自带越界回退(f≥脚本长返回{})
        inp = macro_script(f)
        try:
            r = env.step(inp or {}, opp_inp)
        except Exception:
            break
        if r is None:
            break
        left, right = r[0], r[1]
        if my_hp0 is None:
            my_hp0 = left["hp"]
            opp_hp0 = right["hp"]
        if opp_driver is not None:
            try:
                opp_inp = opp_driver.frame_input(
                    right, left, r[2] if len(r) > 2 else {},
                    r[3] if len(r) > 3 else [], []) or {}
            except Exception:
                opp_inp = {}
        traj.append({
            "f": f, "my_hp": left["hp"], "opp_hp": right["hp"],
            "my_a": left["action"], "opp_a": right["action"],
            "my_x": left["position.x"], "opp_x": right["position.x"],
            "hitStop": left["hitStop"],
        })
    if not traj:
        return None
    return {
        "my_hp_delta": traj[-1]["my_hp"] - my_hp0,
        "opp_hp_delta": traj[-1]["opp_hp"] - opp_hp0,
        "frames": len(traj),
        "end_state": {
            "my_hp": traj[-1]["my_hp"], "opp_hp": traj[-1]["opp_hp"],
            "dx": abs(traj[-1]["opp_x"] - traj[-1]["my_x"]),
        },
        "traj_summary": [
            {"f": t["f"], "dh": t["opp_hp"] - opp_hp0}
            for t in traj[::10]   # 每10帧采样
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--scenario', default='mid_range')
    ap.add_argument('--output', default=None)
    ap.add_argument('--opp-model', action='store_true',
                    help='E1-v2: 对手换模型驱动(默认挂机)')
    args = ap.parse_args()

    scen = SCENARIOS.get(args.scenario)
    if not scen:
        print('可用场景:', list(SCENARIOS.keys()))
        return 1

    env = EvalEnv(PORT, char_left=args.char, char_right=args.char,
                  vs_com=False, tps=None)
    print('排干intro...')
    for _ in range(240):
        try:
            if env.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        except Exception:
            break

    # E1-v2: 模型驱动对手(镜像=同角色生产模型 — "如果对面会打, 各应对
    # 的代价是多少" — 挂机版只演示可达性, 本版演示真博弈)
    opp_driver = None
    if args.opp_model:
        from side_driver import SideDriver
        store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
        opp_driver = SideDriver(args.char, 'R')
        opp_driver.load(os.path.join(store,
                                     'model_ppo_%s.npz' % args.char))
        print('对手: 模型驱动(%s生产模型)' % args.char)
        opp_driver.reset_match()
    else:
        print('对手: 挂机(加--opp-model切换模型驱动)')

    # 三种应对: 防御 / 前冲攻击 / 后退
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS[args.char]
    macros_by_name = {m[0]: m[1] for m in lib['macros']}

    branches = {}
    for label, names in [
        ('防御', ['立防', '蹲防']),
        ('前冲攻击', ['前冲', 'DA', '5A']),
        ('后退', ['后退', '后跳']),
    ]:
        # 构建宏脚本序列(拼接各宏的键步)
        script = []
        for n in names:
            if n in macros_by_name:
                for ks, fr in macros_by_name[n]:
                    if not isinstance(ks, str):
                        script.append((tuple(ks), fr))
        if not script:
            print('  %s: 无可用宏' % label)
            continue
        # 展开为逐帧输入函数
        frames_list = []
        for ks, fr in script:
            inp = {}
            for k in ks:
                if k == 'right':
                    inp['H'] = 1
                elif k == 'left':
                    inp['H'] = -1
                elif k == 'up':
                    inp['V'] = -1
                elif k == 'down':
                    inp['V'] = 1
                elif k in ('A', 'B', 'C', 'D'):
                    inp[k] = True
            frames_list.extend([inp] * int(fr))

        def mk_input(fl):
            def _inp(f):
                return fl[f] if f < len(fl) else {}
            return _inp

        print('执行分支: %s (%d帧)...' % (label, len(frames_list)))
        result = run_branch(env, scen, mk_input(frames_list),
                                opp_driver=opp_driver)
        if result:
            branches[label] = result
            print('  %s: 我方HP%+d 对手HP%+d %d帧'
                  % (label, result['my_hp_delta'],
                     result['opp_hp_delta'], result['frames']))
        else:
            print('  %s: 采集失败' % label)

    # 输出报告
    report = {
        'scenario': args.scenario,
        'desc': scen['desc'],
        'char': args.char,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'branches': branches,
    }
    out = args.output or os.path.join(
        HERE, 'branch_demo_%s_%s.json' % (args.char, args.scenario))
    with open(out, 'w', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('\n报告:', out)
    print('场景: %s' % scen['desc'])
    for label, r in branches.items():
        print('  %s: 我%+d 对%+d | 终局HP %d/%d 距离%d'
              % (label, r['my_hp_delta'], r['opp_hp_delta'],
                 r['end_state']['my_hp'], r['end_state']['opp_hp'],
                 r['end_state']['dx']))

    try:
        env.close()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
