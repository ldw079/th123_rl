# -*- coding: utf-8 -*-
"""trailmod notation parser v2: 复合记谱(hj9/j66/d623b/66/44...)拆成原始步骤(proxy)."""
import json
import re

IN = r'D:\temp\combo_corpus_trailmod_transcribed_20261027.json'
OUT = r'D:\temp\combo_corpus_trailmod_parsed_v2_20261027.json'
MAP66 = {'66': '6', '44': '4', '88': '8', '22': '2', '33': '3', '11': '1',
         '77': '7', '99': '9'}


def parse_token(t):
    t = t.strip()
    if not t:
        return []
    wait = None
    m = re.search(r'\[(\d+)\]', t)
    if m:
        wait = int(m.group(1))
        t = t[:m.start()] + t[m.end():]
    m = re.search(r':(\d+)$', t)
    if m:
        wait = int(m.group(1))
        t = t[:m.start()]
    t = t.lstrip('!')
    steps = []
    # 前缀 h(大跳)/hj(高跳)/j(跳)/d(dash)
    pre = ''
    while t and t[0].isalpha() and t[0] not in 'abcd':
        pre += t[0]
        t = t[1:]
    dirs = re.findall(r'\d+', t)
    keys = [c for c in t if c in 'abcd']
    for d in dirs:
        d2 = MAP66.get(d, d)
        steps.append({'dir': d2[:1], 'keys': [], 'wait': None})
    for k in keys:
        steps.append({'dir': (dirs[-1] if dirs else None), 'keys': [k],
                      'wait': wait})
    if not steps and (pre or keys):
        steps.append({'dir': None, 'keys': keys, 'wait': wait})
    if steps:
        steps[-1]['wait'] = wait if wait is not None else steps[-1]['wait']
    return steps


def main():
    d = json.load(open(IN, encoding='utf-8'))
    rows = []
    for r in d.get('trial_combos') or []:
        toks = (r.get('expected') or '').split()
        steps = []
        for t in toks:
            steps += parse_token(t)
        rows.append({'file': r['file'], 'char': r.get('char'),
                     'expected': r.get('expected'), 'steps': steps,
                     'n_steps': len(steps),
                     'explicit_inputs': r.get('explicit_inputs')})
    d['parsed_v2'] = rows
    json.dump(d, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # coverage: keys subset a-d, dir 1-9
    ts = sum(r['n_steps'] for r in rows)
    ok = 0
    for r in rows:
        for st in r['steps']:
            if all(k in 'abcd' for k in st['keys']) and \
                    (st['dir'] is None or st['dir'] in '123456789'):
                ok += 1
    print(json.dumps({'trials': len(rows), 'steps': ts,
                      'expressible_rate': round(ok / max(1, ts), 4),
                      'out': OUT}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
