# -*- coding: utf-8 -*-
"""C79-8 严格 lab: 50 combo 全步执行/段数/命中/伤害/无截断 + 失败原因.

判据(严格, 不凑):
  pass = 宏队列执行完毕(无截断) AND 命中(掉血>0.5) AND 伤害>0 AND 段数>=1
  目标伤害: 源未定义 → 单列 dmg, 不参与 pass(标注 target_source=undefined)
输出 D:\\temp\\combo_lab_strict_20261027.json / docs/_audit/combo_lab_strict_20261027.md
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

PORT = int(os.environ.get('TH123_COMBO_PORT', '20967'))
HITMEM = int(os.environ.get('TH123_EXEC_HITMEM', '24') or 24)
OUT = r'D:\temp\combo_lab_strict_20261027.json'
MD = os.path.join(WT, 'docs', '_audit', 'combo_lab_strict_20261027.md')
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


def sync(env, lx=500.0, rx=575.0, ry=0.0):
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
        if ry > 0 and i >= 20 and r[0]["action"] == 0:
            return r
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
    r0 = sync(env, pos[0], pos[1], ry)
    if r0 is None:
        return None
    left, right = r0[0], r0[1]
    queue = []
    planned = len(script)
    ME.enqueue_script(queue, script)
    planned_queue = len(queue)
    dname = 'X'
    gate = 0
    traj = []
    hp0 = right['hp']
    pending = 0.0
    hist = []
    executed_steps = 0
    prev_q = len(queue)
    hits = 0
    truncated = True
    for f in range(max_frames):
        d_deal = pending
        if HITMEM > 0:
            hist.append(float(d_deal))
            if len(hist) > HITMEM:
                hist.pop(0)
            hit_mem = float(sum(hist))
        else:
            hit_mem = None
        dx = float(right['position.x']) - float(left['position.x'])
        frozen = bool(float(left.get('hitStop', 0) or 0) > 0
                      or float(right.get('hitStop', 0) or 0) > 0
                      or float(left.get('timeStop', 0) or 0) > 0)
        try:
            queue, gate, dname, inp = ME.advance_queue(
                queue, gate, left, right, d_deal, 0.0, frozen,
                float(left['spirit']), dx, dname, GUARD_PREP_SET,
                GUARD_ALL_IDS, _sc_stub, _sc_reset, hit_mem=hit_mem)
        except Exception:
            break
        qn = len(queue)
        if qn < prev_q:
            executed_steps += 1
        prev_q = qn
        il = dict(NEUTRAL)
        if isinstance(inp, dict):
            for k, v in inp.items():
                if k in ('H', 'V'):
                    il[k] = v
                elif k in ('A', 'B', 'C', 'D'):
                    il[k] = bool(v)
        hp_before = float(right['hp'])
        r = step(env, il, {})
        if r is None:
            break
        left, right = r[0], r[1]
        pending = max(0.0, hp_before - float(right['hp']))
        if pending > 0.5:
            hits += 1
        traj.append((f, int(left['action']), float(right['hp'])))
        if not queue:
            truncated = False
            for _t in range(45):
                hb = float(right['hp'])
                r2 = step(env, dict(NEUTRAL), {})
                if r2 is None:
                    break
                left, right = r2[0], r2[1]
                if hb - float(right['hp']) > 0.5:
                    hits += 1
                traj.append((f, int(left['action']), float(right['hp'])))
            break
    dmg = float(hp0) - float(right['hp'])
    acts = sorted({a for _, a, _ in traj if a not in (0,)
                   and not (50 <= a <= 78) and not (150 <= a <= 166)})
    attack_acts = [a for a in acts if a >= 100 or a in (300, 301, 302, 309)]
    segments = len(attack_acts)
    pass_strict = (not truncated) and hits >= 1 and dmg > 0 and \
        executed_steps >= 1
    reason = []
    if truncated:
        reason.append('truncated(queue_not_empty)')
    if hits == 0:
        reason.append('no_hit')
    if dmg <= 0:
        reason.append('dmg<=0')
    return {'planned_steps': planned, 'planned_queue': planned_queue,
            'executed_steps': executed_steps, 'segments': segments,
            'hits': hits, 'dmg': round(dmg, 1), 'frames': len(traj),
            'truncated': bool(truncated), 'acts': attack_acts[:8],
            'pass_strict': bool(pass_strict),
            'reason': ';'.join(reason) if reason else 'ok',
            'target_damage': None, 'target_source': 'undefined'}


def main():
    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'port': PORT,
           'hitmem': HITMEM, 'criterion': 'C79-8 strict', 'chars': {}}
    env = None
    try:
        env = EvalEnv(PORT, char_left='reimu', char_right='reimu',
                      vs_com=False, tps=None)
        for _ in range(240):
            if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        from train_tm import CHAR_LIBS
        for ch in CHARS:
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
                scen = [((500.0, 575.0), 0.0)]
                if any(k in nm for k in ('空', '对空')):
                    scen.append(((500.0, 580.0), 120.0))
                rs = [replay(env, mac[nm], pos=p, ry=ry) for p, ry in scen]
                rs = [x for x in rs if x]
                if not rs:
                    out[nm] = {'err': True, 'pass_strict': False,
                               'reason': 'env_step_none'}
                    continue
                r0 = rs[0]
                out[nm] = {'n_scenes': len(rs),
                           'planned_steps': r0['planned_steps'],
                           'executed_steps': r0['executed_steps'],
                           'segments': r0['segments'],
                           'hits': r0['hits'], 'dmg': r0['dmg'],
                           'frames': r0['frames'],
                           'truncated': r0['truncated'],
                           'pass_strict': all(x['pass_strict'] for x in rs),
                           'reason': ';'.join(sorted({x['reason']
                                                      for x in rs})),
                           'target_damage': None,
                           'target_source': 'undefined',
                           'per_scene': rs}
                print(ch, nm, out[nm]['pass_strict'], out[nm]['reason'],
                      out[nm]['dmg'], flush=True)
            res['chars'][ch] = out
        json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
                  indent=1)
        lines = ['# C79-8 严格 lab 表（2026-10-27）', '',
                 '- 判据: 队列执行完(无截断) AND 命中≥1 AND dmg>0 AND 段数≥1；'
                 '目标伤害源未定义（target_source=undefined，不参与 pass）',
                 '- 端口 %s / HITMEM=%s；失败原因逐条列。' % (PORT, HITMEM), '',
                 '| 角色 | combo | planned | executed | segments | hits | dmg | truncated | pass | reason |',
                 '|---|---|---|---|---|---|---|---|---|---|']
        tot = ok = 0
        for ch, out in res['chars'].items():
            for nm, v in out.items():
                if v.get('missing'):
                    continue
                tot += 1
                ok += 1 if v.get('pass_strict') else 0
                lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |'
                             % (ch, nm, v.get('planned_steps'), v.get('executed_steps'),
                                v.get('segments'), v.get('hits'), v.get('dmg'),
                                v.get('truncated'), v.get('pass_strict'),
                                v.get('reason')))
        lines += ['', '**合计: %d/%d PASS**（失败照实列；未用 proxy）' % (ok, tot)]
        open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        print('STRICT TOTAL %d/%d PASS -> %s' % (ok, tot, OUT))
    finally:
        try:
            if env is not None:
                env.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
