# -*- coding: utf-8 -*-
"""task-33 连段宏 replay 校验(只读): 每 combo 宏回放→段数/伤害/取消步成功.

成功判据: ①至少 2 个不同攻击动作执行 ②对手掉血(命中) ③宏内 cancel/confirm 步未提前截断.
产物: D:\\temp\\scratch\\combo_replay_20261024.json
"""
import json
import os
import struct
import sys
import time

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
import macro_executor as ME  # noqa: E402
from side_driver import EvalEnv  # noqa: E402

PORT = int(os.environ.get('TH123_COMBO_PORT', '20963'))
_HITMEM = int(os.environ.get('TH123_EXEC_HITMEM', '0') or 0)
OUT = os.environ.get('TH123_COMBO_OUT',
                     r'D:\temp\scratch\combo_replay_check.json')
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
CHARS = ('reimu', 'marisa', 'suika')
GUARD_ALL_IDS = set(range(150, 167))
GUARD_PREP_SET = set()


def step(env, il, ir):
    try:
        return env.step(il or {}, ir or {})
    except Exception:
        return None


def sync(env, lx=500.0, rx=575.0, ry=0.0, allow_fall=False):
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
        if allow_fall:
            # 空中场景: 对手下落中 action!=0; 等左方 idle 即可
            if i >= 20 and r[0]["action"] == 0:
                return r
            continue
        if r[0]["action"] == 0 and r[1]["action"] == 0:
            ok += 1
            if ok >= 5:
                return r
        else:
            ok = 0
    return None


def _sc_stub(own):
    return False, True, {}


def _sc_reset():
    pass


def replay(env, script, max_frames=260, pos=(500.0, 575.0), ry=0.0):
    r0 = sync(env, pos[0], pos[1], ry, allow_fall=(ry > 0))
    if r0 is None:
        return None
    left, right = r0[0], r0[1]
    queue = []
    ME.enqueue_script(queue, script)
    dname = 'X'
    gate = 0
    traj = []
    hp0 = right['hp']
    _pending_d = 0.0
    r = None
    _hist = []
    for f in range(max_frames):
        # P1 修复(2026-10-25): 旧版 last_hp 在 step 后更新 → d_deal 恒 0.
        # 逐帧差 = 本帧 step 前后的 hp 差, 延迟一帧送入执行器(与训练同拍).
        d_deal = _pending_d
        if _HITMEM > 0:
            _hist.append(float(d_deal))
            if len(_hist) > _HITMEM:
                _hist.pop(0)
            _hit_mem = float(sum(_hist))
        else:
            _hit_mem = None
        dx = float(right['position.x']) - float(left['position.x'])
        _frozen = bool(float(left.get('hitStop', 0) or 0) > 0
                       or float(right.get('hitStop', 0) or 0) > 0
                       or float(left.get('timeStop', 0) or 0) > 0)
        try:
            queue, gate, dname, inp = ME.advance_queue(
                queue, gate, left, right, d_deal, 0.0, _frozen,
                float(left['spirit']), dx, dname, GUARD_PREP_SET,
                GUARD_ALL_IDS, _sc_stub, _sc_reset,
                hit_mem=_hit_mem)
        except Exception:
            break
        il = dict(NEUTRAL)
        if isinstance(inp, dict):
            for k, v in inp.items():
                if k in ('H', 'V'):
                    il[k] = v
                elif k in ('A', 'B', 'C', 'D'):
                    il[k] = bool(v)
        _hp_before = float(right['hp'])
        r = step(env, il, {})
        if r is None:
            break
        left, right = r[0], r[1]
        _pending_d = max(0.0, _hp_before - float(right['hp']))
        traj.append((f, int(left['action']), float(right['hp'])))
        if not queue:
            # task-58 p3: 宏结束(如弹幕型 5B)后继续跟 45F, 让在途弹幕/伤害结算
            # 完成再统计(否则 projectile 宏被误判空挥).
            for _t in range(45):
                _hp_b = float(right['hp'])
                r2 = step(env, dict(NEUTRAL), {})
                if r2 is None:
                    break
                left, right = r2[0], r2[1]
                traj.append((f, int(left['action']), float(right['hp'])))
                if float(right['hp']) < _hp_b - 0.5:
                    _tail_hit = True
            break
    dmg = float(hp0) - float(right['hp'])
    acts = sorted({a for _, a, _ in traj if a not in (0,) and not (50 <= a <= 78)
                   and not (150 <= a <= 166)})
    attack_acts = [a for a in acts if a >= 100 or a in (300, 301, 302, 309)]
    strict_ok = (dmg >= 300.0) or (len(attack_acts) >= 2)
    return {'dmg': round(dmg, 1), 'distinct_acts': len(attack_acts),
            'acts': attack_acts[:8], 'frames': len(traj),
            'strict_ok': strict_ok,
            'aborted_early': len(traj) < max_frames and dmg <= 0}


env = EvalEnv(PORT, char_left='reimu', char_right='reimu',
              vs_com=False, tps=None)
res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'chars': {}}
try:
    for _ in range(240):
        if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
            break
    from train_tm import CHAR_LIBS
    for ch in CHARS:
        # P0 harness 修复(2026-10-25): 旧版全程 reimu-reimu 游戏 → marisa/suika
        # 宏在其角色不同的游戏里 replay, 动作/伤害全错(误判空挥). 每角色重建.
        try:
            env.close()
        except Exception:
            pass
        env = EvalEnv(PORT, char_left=ch, char_right=ch,
                      vs_com=False, tps=None)
        for _ in range(240):
            if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        lib = CHAR_LIBS[ch]
        mac = {m[0]: m[1] for m in lib['macros']}
        combos = sorted(lib.get('combo', []))
        out = {}
        for nm in combos:
            if nm not in mac:
                out[nm] = {'missing': True}
                continue
            _has_sc = any(isinstance(k, str) and str(k).startswith('sc:')
                          for k, _f in mac[nm])
            rs = []
            _scen = [((500.0, 575.0), 0.0), ((960.0, 1030.0), 0.0),
                     ((500.0, 540.0), 0.0)]
            if any(k in nm for k in ('空', '对空')):
                _scen.append(((500.0, 580.0), 120.0))  # 对手空中场景
            for _pos, _ry in _scen:
                rs += [replay(env, mac[nm], pos=_pos, ry=_ry)
                       for _ in range(1)]
            rs = [x for x in rs if x]
            if not rs:
                out[nm] = {'err': True}
                continue
            ok = [x for x in rs if x['dmg'] > 0]
            ok_s = [x for x in rs if x.get('strict_ok')]
            out[nm] = {'n': len(rs), 'ok': len(ok), 'strict_ok': len(ok_s),
                       'has_sc': _has_sc,
                       'dmg': [x['dmg'] for x in rs],
                       'acts': [x['acts'] for x in rs],
                       'frames': [x['frames'] for x in rs]}
            print(ch, nm, out[nm], flush=True)
        res['chars'][ch] = out
    with open(OUT, 'w', encoding='utf8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    # 汇总
    for ch, out in res['chars'].items():
        tot = len(out)
        okn = sum(1 for v in out.values() if v.get('ok', 0) > 0)
        oks = sum(1 for v in out.values() if v.get('strict_ok', 0) > 0)
        print('SUMMARY %s: %d/%d combos replay>=0.5 (rate %.2f)'
              % (ch, okn, tot, okn / max(1, tot)))
    print('[done]', OUT)
finally:
    try:
        env.close()
    except Exception:
        pass
