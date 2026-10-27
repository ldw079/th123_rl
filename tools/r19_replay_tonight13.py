# -*- coding: utf-8 -*-
"""今晚 13 条 RL-AI rep 单独指标(排除旧 AI 代际); 分模型角色+合计."""
import json
import statistics as st

SRC = r'D:\temp\r19_replay_metrics_20261027.json'
OUTJ = r'D:\temp\r19_replay_metrics_tonight13_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\r19_replay_metrics_tonight13_20261027.md'
d = json.load(open(SRC, encoding='utf-8'))
rows = [r for r in d['rows'] if r.get('tonight') and r.get('model')
        and r['model'].get('frames')]
KEYS = ('dec_per_sec', 'macro_avg_frames', 'attack_rate', 'melee_rate',
        'ranged_rate', 'approach_rate', 'back_rate', 'jump_rate')


def med(rs, key):
    xs = [r['model'][key] for r in rs if key in r['model']]
    return round(st.median(xs), 3) if xs else None


groups = {}
for r in rows:
    groups.setdefault(r.get('char_model', '?'), []).append(r)
res = {'n': len(rows), 'groups': {}, 'note': (
    '仅 26-10-27_19-* RL-AI reps；dec/sec=输入变化/(frames/60)；'
    'react=人类攻击后12F模型后/ dash/跳 代理，非擦弹；无HP/弹幕→擦弹/被弹/whiff 不可得')}
for ch, rs in groups.items():
    res['groups'][ch] = {'n': len(rs),
                         **{k: med(rs, k) for k in KEYS}}
res['all'] = {k: med(rows, k) for k in KEYS}
res['scores'] = [r['file'] for r in rows]
json.dump(res, open(OUTJ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
lines = ['# 今晚 13 条 RL-AI rep 指标（2026-10-27 19:16–19:35）', '',
         '- 仅 `26-10-27_19-*` RL-AI rep；旧 AI/其它来源已排除。',
         '- 定义：dec/sec=输入变化/(frames/60)；react=人类攻击后12F模型 back/dash/jump 代理；'
         '**rep 无 HP/弹幕 → 擦弹/被弹/whiff 不可得**。', '',
         '| 模型角色 | n | dec/sec | macro_frames | attack | melee | ranged | approach | back | jump |',
         '|---|---|---|---|---|---|---|---|---|---|']
for ch, g in sorted(res['groups'].items()):
    lines.append('| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        ch, g['n'], g['dec_per_sec'], g['macro_avg_frames'],
        g['attack_rate'], g['melee_rate'], g['ranged_rate'],
        g['approach_rate'], g['back_rate'], g['jump_rate']))
lines += ['', '**合计**: %s' % json.dumps(res['all'], ensure_ascii=False), '',
          '## 逐局', '']
for r in rows:
    lines.append('- %s | 模型 %s | dec/s %s | attack %s | approach %s' % (
        r['file'], r.get('char_model'), r['model'].get('dec_per_sec'),
        r['model'].get('attack_rate'), r['model'].get('approach_rate')))
open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print(json.dumps(res, ensure_ascii=False)[:1200])
