# -*- coding: utf-8 -*-
"""C79-8 v2: 逐 scene 行 + target_damage 独立来源(历史 p4 golden ×0.9 容差) + manifest."""
import json
import os
import hashlib
import sys

STRICT = r'D:\temp\combo_lab_strict_20261027.json'
P4 = r'D:\temp\scratch\combo_replay_p4.json'
OUT = r'D:\temp\combo_lab_strict_v2_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\combo_lab_strict_v2_20261027.md'
REP_DIR = r'D:\temp\combo_lab_replays_20261027'

d = json.load(open(STRICT, encoding='utf-8'))
p4 = json.load(open(P4, encoding='utf-8')) if os.path.exists(P4) else {}


def target(ch, nm):
    try:
        v = p4.get('chars', {}).get(ch, {}).get(nm)
        if not v:
            return None, 'undefined'
        ds = [x for x in (v.get('dmg') or []) if isinstance(x, (int, float))]
        if not ds:
            return None, 'undefined'
        return round(max(ds) * 0.9, 1), 'p4_max*0.9(tolerance 10%)'
    except Exception:
        return None, 'undefined'


rows = []
for ch, out in d.get('chars', {}).items():
    for nm, v in out.items():
        if v.get('missing') or v.get('err'):
            rows.append({'char': ch, 'combo': nm, 'scene': -1,
                         'pass': False, 'reason': 'missing/err'})
            continue
        tgt, tsrc = target(ch, nm)
        scenes = v.get('per_scene') or [v]
        for si, s in enumerate(scenes):
            dmg = s.get('dmg', 0.0)
            ps = bool(s.get('pass_strict'))
            if tgt is None:
                p = False
                reason = (s.get('reason') or '') + ';target_undefined'
                judged = 'unjudged'
            else:
                p = ps and dmg >= tgt
                judged = 'judged'
                reason = s.get('reason') if p else (
                    (s.get('reason') or '') + ';dmg<target')
            rows.append({'char': ch, 'combo': nm, 'scene': si,
                         'planned_steps': s.get('planned_steps'),
                         'executed_steps': s.get('executed_steps'),
                         'segments': s.get('segments'),
                         'hits': s.get('hits'), 'dmg': dmg,
                         'target_damage': tgt, 'target_source': tsrc,
                         'truncated': s.get('truncated'),
                         'pass_strict': ps, 'target_judged': judged,
                         'pass': p, 'reason': reason,
                         'rep': None,
                         'rep_note': 'EvalEnv 未开录像; 见 frame_trace/替代验证'})
json.dump({'rows': rows, 'note': ('per-scene; target=历史 p4 max*0.9; '
                                  'rep=EvalEnv 未产生; 兼容性见 manifest')},
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
os.makedirs(REP_DIR, exist_ok=True)
# 示例 manifest: 第一条 pass 且 target_judged
ex = next((r for r in rows if r.get('pass') and r.get('target_judged') == 'judged'), None)
man = {'example': ex,
       'how_to_verify': ('lab 由 EvalEnv(COM) 运行, 未开启游戏录像 → 无 .rep; '
                         '替代: frame_trace/伤害曲线/逐帧输入; 原版回放需游戏内录像开启'),
       'sha1_note': 'no rep produced'}
json.dump(man, open(os.path.join(REP_DIR, 'verify_manifest_example.json'), 'w',
                    encoding='utf-8'), ensure_ascii=False, indent=1)
# md
lines = ['# C79-8 严格 lab v2（逐 scene; 2026-10-27）', '',
         '- target_damage = 历史 p4 最大伤害 ×0.9（容差 10%，来源逐条标注）；'
         '无历史目标 → target_undefined 不判 pass。', '',
         '| 角色 | combo | scene | planned | executed | segments | hits | dmg | target | pass | reason |',
         '|---|---|---|---|---|---|---|---|---|---|---|']
for r in rows:
    lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        r.get('char'), r.get('combo'), r.get('scene'),
        r.get('planned_steps'), r.get('executed_steps'), r.get('segments'),
        r.get('hits'), r.get('dmg'), r.get('target_damage'),
        r.get('pass'), r.get('reason')))
tot = len(rows)
ok = sum(1 for r in rows if r.get('pass'))
lines += ['', '**合计: %d/%d 行 pass（含 target_undefined 未判）**' % (ok, tot)]
open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print(json.dumps({'rows': tot, 'pass': ok, 'example': ex}, ensure_ascii=False)[:800])
