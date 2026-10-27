# -*- coding: utf-8 -*-
"""trailmod notation -> 宏步骤 proxy 转写（只读; 不执行 exe/不改原目录）.

把 expected 记谱（如 `5aaaa !6[2]:53 ...`）拆成 token 步骤:
  - 方向/数字前缀(5/6/8/.../hj/j/2/4) + 按键 a/b/c/d + :帧数/[N] 时长
输出 `combo_corpus_trailmod_20261027_v2.json`；status=transcribed-proxy/notation-only。
"""
import json
import re

IN = r'D:\temp\combo_corpus_trailmod_20261027.json'
OUT = r'D:\temp\combo_corpus_trailmod_transcribed_20261027.json'


def parse(expected):
    if not expected:
        return []
    toks = expected.split()
    steps = []
    for t in toks:
        base = t
        wait = None
        m = re.match(r'^!?(.*?)(?:\[(\d+)\])?(?::(\d+))?$', base)
        if m:
            core, br, col = m.group(1), m.group(2), m.group(3)
            if br:
                wait = int(br)
            if col:
                wait = int(col)
        else:
            core = base
        keys = [c for c in core if c in 'abcd']
        dirs = re.sub(r'[^0-9]', '', core)
        steps.append({'raw': t, 'keys': keys, 'dir': dirs or None,
                      'wait': wait})
    return steps


def main():
    d = json.load(open(IN, encoding='utf-8'))
    rows = []
    for t in d.get('trial_combos') or []:
        steps = parse(t.get('expected'))
        rows.append({'file': t['file'], 'char': t.get('char'),
                     'expected': t.get('expected'), 'n_steps': len(steps),
                     'steps': steps, 'explicit_inputs': t.get('explicit_inputs'),
                     'status': 'transcribed-proxy' if steps else 'notation-only',
                     'needs_replay_validation': True})
    d['transcribed'] = rows
    d['transcribe_note'] = ('notation→宏步骤 proxy 转写; 必须严格 replay 验证; '
                            '8 条 explicit_inputs 可直接走 parser; '
                            '其余 notation-only 需人工复核')
    json.dump(d, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({'trials': len(rows),
                      'transcribed': sum(1 for r in rows if r['steps']),
                      'explicit': sum(1 for r in rows if r['explicit_inputs']),
                      'total_steps': sum(r['n_steps'] for r in rows)},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
