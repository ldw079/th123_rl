# -*- coding: utf-8 -*-
"""R19 VS_PLAYER rep 独立真值: 模型(RL-AI) vs 人类 行为指标.

rep 只读; 文件名=26-10-27_19-35-04_深圳人形(帕秋莉)_RL-AI(萃香)_(2:0_负).rep
side0=左(深圳人形=人类), side1=右(RL-AI=模型).
指标: decisions/sec, macro_avg_frames, attack_rate(A/B/C/D), melee(A)/ranged(B/C),
      approach/back, jump, 受人类攻击后 12F 反应代理; 无 HP/弹幕→擦弹/whiff 不可得.
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa
from train_tm import CHAR_LIBS  # noqa

ROOT = r'D:\touhou\hisoutensoku2026-06-15\th123\replay\【本地Rep】\VS_PLAYER'
OUT = r'D:\temp\r19_replay_metrics_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\r19_replay_metrics_20261027.md'
A, B, C, D = 1 << 4, 1 << 5, 1 << 6, 1 << 7
UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8


def name_of(cid):
    try:
        return CHAR_LIBS.get(int(cid), {}).get('name') or str(cid)
    except Exception:
        return str(cid)


def metrics(seq, side):
    n = len(seq)
    if not n:
        return {}
    chg = sum(1 for i in range(1, n) if seq[i] != seq[i - 1])
    runs = sum(1 for i in range(1, n) if seq[i] != seq[i - 1])
    fwd = RIGHT if side == 0 else LEFT
    back = LEFT if side == 0 else RIGHT
    atk = sum(1 for x in seq if int(x) & (A | B | C | D))
    melee = sum(1 for x in seq if int(x) & A)
    ranged = sum(1 for x in seq if int(x) & (B | C))
    fw = sum(1 for x in seq if int(x) & fwd)
    bk = sum(1 for x in seq if int(x) & back)
    jmp = sum(1 for x in seq if int(x) & UP)
    return {'frames': n, 'duration_sec': round(n / 60, 2),
            'decisions': chg,
            'dec_per_sec': round(chg / max(1e-9, n / 60), 2),
            'macro_avg_frames': round(n / max(1, runs + 1), 2),
            'attack_rate': round(atk / n, 3),
            'melee_rate': round(melee / n, 3),
            'ranged_rate': round(ranged / n, 3),
            'approach_rate': round(fw / n, 3),
            'back_rate': round(bk / n, 3),
            'jump_rate': round(jmp / n, 3)}


def react(h, m, window=12):
    n = min(len(h), len(m))
    starts = []
    prev = 0
    for i in range(n):
        a = int(h[i]) & (A | B | C | D)
        if a and not (prev & (A | B | C | D)):
            starts.append(i)
        prev = int(h[i])
    reacted = 0
    delays = []
    for s in starts:
        for j in range(s + 1, min(n, s + 1 + window)):
            x = int(m[j])
            if (x & (LEFT | D | UP)):
                reacted += 1
                delays.append(j - s)
                break
    return {'starts': len(starts), 'reacted': reacted,
            'rate': round(reacted / max(1, len(starts)), 3),
            'avg_delay': round(sum(delays) / max(1, len(delays)), 2)}


def main():
    files = sorted(glob.glob(os.path.join(ROOT, '*.rep')))
    rows = []
    for p in files:
        nm = os.path.basename(p)
        rec = {'file': nm,
               'sha1_12': hashlib.sha1(open(p, 'rb').read()).hexdigest()[:12],
               'mtime': os.path.getmtime(p), 'bytes': os.path.getsize(p)}
        try:
            r = parse_rep_file(p)
            arr = inputs_by_side(list(r.inputs))
            h = [int(x) for x in arr[:, 0]]
            m = [int(x) for x in arr[:, 1]]
            rec['char_human'] = name_of(getattr(r, 'char_x', None))
            rec['char_model'] = name_of(getattr(r, 'char_y', None))
            rec['human'] = metrics(h, 0)
            rec['model'] = metrics(m, 1)
            rec['react'] = react(h, m)
            rec['tonight'] = nm.startswith('26-10-27_19-')
        except Exception as e:
            rec['error'] = repr(e)[:100]
        rows.append(rec)
    # aggregate
    def agg(key):
        ks = ('dec_per_sec', 'macro_avg_frames', 'attack_rate', 'melee_rate',
              'ranged_rate', 'approach_rate', 'back_rate', 'jump_rate')
        v = {k: [] for k in ks}
        for r in rows:
            if key in r and r[key]:
                for k in ks:
                    if k in r[key]:
                        v[k].append(r[key][k])
        import statistics as _st
        return {k: round(_st.median(x), 3) for k, x in v.items() if x}
    reacts = [r['react'] for r in rows if 'react' in r]
    summary = {'n_reps': len(rows),
               'model_avg': agg('model'), 'human_avg': agg('human'),
               'react_avg': {'rate': round(sum(x['rate'] for x in reacts)
                                           / max(1, len(reacts)), 3),
                             'delay': round(sum(x['avg_delay'] for x in reacts)
                                            / max(1, len(reacts)), 2),
                             'threats': sum(x['starts'] for x in reacts)},
               'tonight_reps': sum(1 for r in rows if r.get('tonight'))}
    json.dump({'summary': summary, 'rows': rows},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    lines = ['# R19 VS_PLAYER rep 独立真值（2026-10-27）', '',
             '- rep 目录 `%s`；132 个；解析 %d；今晚 %d' % (
                 ROOT, len(rows), summary['tonight_reps']),
             '- side0=深圳人形(人类), side1=RL-AI(模型)；只读/合法回放；'
             '无 HP/弹幕→擦弹/whiff 不可得（标注）。', '',
             '| 指标 | 模型 | 人类 |', '|---|---|---|']
    for k in ('dec_per_sec', 'macro_avg_frames', 'attack_rate', 'melee_rate',
              'ranged_rate', 'approach_rate', 'back_rate', 'jump_rate'):
        lines.append('| %s | %s | %s |' % (k, summary['model_avg'][k],
                                           summary['human_avg'][k]))
    lines += ['', '- 受人类攻击后 12F 反应代理：rate=%s delay=%sF threats=%s' % (
        summary['react_avg']['rate'], summary['react_avg']['delay'],
        summary['react_avg']['threats']),
        '', '| 文件 | 人类角色 | 模型角色 | sha1 |', '|---|---|---|---|']
    for r in rows[:20]:
        lines.append('| %s | %s | %s | %s |' % (
            r['file'], r.get('char_human'), r.get('char_model'),
            r.get('sha1_12')))
    lines += ['', '说明：模型侧攻击/远程/近身/approach 均由输入位解码；'
              '擦弹/被弹需帧状态，rep 不含，标为不可得。']
    open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps({'summary': summary, 'out': OUT},
                     ensure_ascii=False)[:1000])


if __name__ == '__main__':
    sys.exit(main())
