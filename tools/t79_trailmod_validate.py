# -*- coding: utf-8 -*-
"""task-79 trailmod 静态可转写性验证 + 5 条 replay 待验清单."""
import json
import sys

IN = r'D:\temp\combo_corpus_trailmod_transcribed_20261027.json'
OUT = r'D:\temp\t79_trailmod_validation_20261027.json'
KEYS = set('abcd')
DIRS = {str(i) for i in range(1, 10)}
ALLOWED_DUR = {1, 2, 3, 4, 6, 8, 10, 12, 16}

d = json.load(open(IN, encoding='utf-8'))
rows = d.get('transcribed') or []
res = {'trials': len(rows), 'steps': 0, 'steps_expressible': 0,
       'trials_all_steps_expressible': 0, 'needs_manual': [],
       'replay_candidates': []}
for r in rows:
    ok_all = True
    for st in r.get('steps') or []:
        res['steps'] += 1
        keys_ok = all(k in KEYS for k in st.get('keys', []))
        dir_ok = (st.get('dir') is None) or (st.get('dir') in DIRS)
        wait_ok = (st.get('wait') is None) or \
            any(st['wait'] % a == 0 for a in ALLOWED_DUR) or \
            st['wait'] <= 16
        ok = keys_ok and dir_ok and wait_ok
        res['steps_expressible'] += 1 if ok else 0
        ok_all = ok_all and ok
    if ok_all:
        res['trials_all_steps_expressible'] += 1
    else:
        res['needs_manual'].append(r['file'])
    if r.get('explicit_inputs'):
        res['replay_candidates'].append({
            'file': r['file'], 'char': r.get('char'),
            'expected': r.get('expected'),
            'status': 'pending_strict_replay',
            'reason': 'needs isolated game/replay lab (not run yet)'})
res['step_expressible_rate'] = round(
    res['steps_expressible'] / max(1, res['steps']), 4)
res['trial_expressible_rate'] = round(
    res['trials_all_steps_expressible'] / max(1, res['trials']), 4)
res['note'] = ('静态可转写=keys a-d/dir 1-9/wait 可分解; 严格 replay 未跑(5 条候选); '
               'notation-only 需人工复核')
json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps({k: res[k] for k in ('trials', 'steps',
                                      'step_expressible_rate',
                                      'trial_expressible_rate',
                                      'replay_candidates')}, ensure_ascii=False)[:800])
