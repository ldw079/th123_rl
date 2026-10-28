# -*- coding: utf-8 -*-
"""task-81 v0: 直接回放 TrialMode trial JSON 的 inputs, 按原生 score 判据验证.

- trial JSON: player/dummy/pos/weather/skills/inputs[9]=[H,V,A,B,C,D,SC,SW,frames]
- EvalEnv 隔离端口; 逐帧喂 input; 记录 comboLimit/comboDamage/comboCount/hits/dmg
- 判据: score[0] min_hits/min_damage/min_limit (TrialMode 原生)
输出 D:\\temp\\trial_replay_<name>.json
"""
import argparse
import json
import os
import struct
import sys
import time

WT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, WT)
from side_driver import EvalEnv  # noqa: E402

PORT = int(os.environ.get('TH123_TRIAL_PORT', '20968'))
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}


def step(env, il, ir=None):
    try:
        return env.step(il or {}, ir or {})
    except Exception:
        return None


def sync(env, lx, rx, ry=0.0):
    ok = 0
    for i in range(260):
        if i % 40 == 0:
            try:
                env.inst._send(struct.pack("<BHH", 13, 10000, 10000))
                env.inst._send(struct.pack("<B4f", 14, lx, 0.0, rx, ry))
            except Exception:
                pass
        r = step(env, dict(NEUTRAL), dict(NEUTRAL))
        if r is None:
            return None
        if r[0]["action"] == 0 and r[1]["action"] == 0:
            ok += 1
            if ok >= 5:
                return r
        else:
            ok = 0
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trial', required=True)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    d = json.load(open(a.trial, encoding='utf-8'))
    pl = d.get('player') or {}
    du = d.get('dummy') or {}
    lx = float(pl.get('pos', 500))
    rx = float((du.get('pos') or {}).get('x', 575))
    ry = float((du.get('pos') or {}).get('y', 0) or 0)
    print('trial', os.path.basename(a.trial), 'player', pl.get('character'),
          'dummy', du.get('character'), 'pos', lx, rx, ry,
          'inputs', len(d.get('inputs') or []), flush=True)
    env = EvalEnv(PORT, char_left=pl.get('character'),
                  char_right=du.get('character'), vs_com=False, tps=None)
    res = {'trial': a.trial, 'score': d.get('score'),
           'expected': d.get('expected'), 'frames': 0, 'max_limit': 0,
           'max_damage': 0, 'max_count': 0, 'max_hits': 0,
           'pass': False}
    try:
        for _ in range(240):
            if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        r0 = sync(env, lx, rx, ry)
        if r0 is None:
            print('sync failed')
            return 1
        left, right = r0[0], r0[1]
        hp0 = float(right['hp'])
        hits = 0
        for row in d.get('inputs') or []:
            if len(row) < 9:
                continue
            H, V, A, B, C, D, SC, SW, frames = row
            il = {'H': int(H), 'V': int(V), 'A': bool(A), 'B': bool(B),
                  'C': bool(C), 'D': bool(D), 'SC': bool(SC),
                  'SW': bool(SW)}
            for _ in range(int(frames)):
                r = step(env, il, {})
                if r is None:
                    break
                left, right = r[0], r[1]
                res['frames'] += 1
                res['max_limit'] = max(res['max_limit'],
                                       int(left.get('comboLimit', 0) or 0))
                res['max_damage'] = max(res['max_damage'],
                                        int(left.get('comboDamage', 0) or 0))
                res['max_count'] = max(res['max_count'],
                                       int(left.get('comboCount', 0) or 0))
                res['max_hits'] = max(res['max_hits'],
                                      int(left.get('comboDamage', 0) or 0))
                if float(right['hp']) < float(left.get('_last_hp', right['hp'])):
                    hits += 1
                if int(left.get('comboDamage', 0) or 0) > 0:
                    res['max_hits'] = max(res['max_hits'],
                                          int(left.get('comboCount', 0) or 0))
        res['dmg'] = round(hp0 - float(right['hp']), 1)
        sc = (d.get('score') or [{}])[0]
        res['pass'] = (res['max_limit'] >= int(sc.get('min_limit', 0) or 0)
                       and res['dmg'] >= int(sc.get('min_damage', 0) or 0)
                       and res['max_count'] >= int(sc.get('min_hits', 0) or 0))
        out = a.out or os.path.join(r'D:\temp',
                                    'trial_replay_%s.json' %
                                    os.path.splitext(os.path.basename(a.trial))[0])
        json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False,
                  indent=1)
        print(json.dumps(res, ensure_ascii=False)[:1000])
        print('OUT', out)
    finally:
        try:
            env.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
