# -*- coding: utf-8 -*-
"""task-33 帧表离线校准工具(prototype): 回放宏/招式输入, 记录动作帧区间/untech.

产物: D:\\temp\\scratch\\frame_table_20261022.json
格式: {char: {macro: {frames: N, actions: [{id, start, end}], untech: [...]}}}
用于 startup/recovery/untech/无敌帧估算(无官方表时的 replay 校准, 合规)。
"""
import json
import struct
import sys
import time

WT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, WT)
from side_driver import EvalEnv  # noqa: E402

PORT = 20956
OUT = r'D:\temp\scratch\frame_table_20261022.json'
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
DMAP = {'down': ('V', -1), 'up': ('V', 1),
        'left': ('H', -1), 'right': ('H', 1)}
TARGETS = ['5A', '236B', '236C', '623B', '214B', '22C']


def step(env, il, ir):
    try:
        return env.step(il or {}, ir or {})
    except Exception:
        return None


def sync(env, lx=480.0, rx=555.0):
    ok = 0
    for i in range(260):
        if i % 40 == 0:
            try:
                env.inst._send(struct.pack("<BHH", 13, 10000, 10000))
                env.inst._send(struct.pack("<B4f", 14, lx, 0.0, rx, 0.0))
            except Exception:
                pass
        r = step(env, dict(NEUTRAL), dict(NEUTRAL))
        if r is None:
            return False
        if r[0]["action"] == 0 and r[1]["action"] == 0:
            ok += 1
            if ok >= 5:
                return True
        else:
            ok = 0
    return False


def expand(script):
    frames = []
    for keys, fr in script:
        if not isinstance(keys, tuple):
            continue
        d = {}
        for k in keys:
            if k in ('A', 'B', 'C', 'D'):
                d[k] = True
            elif k in DMAP:
                ax, v = DMAP[k]
                d[ax] = v
        frames += [dict(d)] * int(fr)
    return frames


def record(env, script):
    if not sync(env):
        return None
    traj = []
    for f, il in enumerate(expand(script) + [{}] * 30):
        r = step(env, il, {})
        if r is None:
            break
        L = r[0]
        traj.append((f, int(L['action']), int(L.get('untech', 0) or 0),
                     float(L.get('hp', 0))))
    segs = []
    cur = None
    for f, a, u, hp in traj:
        if a != 0 and cur is None:
            cur = [a, f, f]
        elif a != 0 and cur is not None and a == cur[0]:
            cur[2] = f
        elif a != 0 and cur is not None and a != cur[0]:
            segs.append(cur)
            cur = [a, f, f]
        elif a == 0 and cur is not None:
            segs.append(cur)
            cur = None
    if cur:
        segs.append(cur)
    return {'frames': len(traj),
            'actions': [{'id': s[0], 'start': s[1], 'end': s[2]}
                        for s in segs],
            'untech_frames': [f for f, a, u, hp in traj if u > 0][:8],
            'startup': segs[0][1] if segs else None}


def main():
    import macros as M
    lib = {n: s for n, s in M.MACROS}
    env = EvalEnv(PORT, char_left='reimu', char_right='reimu',
                  vs_com=False, tps=None)
    res = {'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'), 'reimu': {}}
    try:
        for _ in range(240):
            if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        for nm in TARGETS:
            if nm not in lib:
                res['reimu'][nm] = {'missing': True}
                print(nm, 'MISSING', flush=True)
                continue
            o = record(env, lib[nm])
            res['reimu'][nm] = o
            print('%s %s' % (nm, o), flush=True)
        with open(OUT, 'w', encoding='utf8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print('[done]', OUT)
    finally:
        try:
            env.close()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
