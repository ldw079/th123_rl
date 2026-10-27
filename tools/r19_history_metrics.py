# -*- coding: utf-8 -*-
"""R19 历史行为指标: human vs model from reps/sessions.

代理口径(rep 无弹幕状态):
  decisions/sec = 输入变化次数 / (frames/60)
  macro_avg_frames = 同输入 run 平均长度
  attack_rate = A/B/C 帧占比; approach_rate = 前方向帧占比(按侧朝向)
  guard_retreat_rate = 后方向帧占比
  react_after_attack = 人类攻击起始后 12F 内模型出现 后方向/dash/jump 的比例与平均延迟
"""
import glob
import json
import os
import sys

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa
from train_tm import CHAR_LIBS  # noqa

SESS = r'C:\Users\96120\Desktop\workplace\th123_rl\tools\human_match_sessions\sess_*.json'
REP_DIRS = [r'D:\temp\th123_models\human_reps',
            r'C:\Users\96120\Desktop\workplace\th123_rl\models\human_reps']
OUT = r'D:\temp\r19_history_behavior_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\r19_history_behavior_20261027.md'
A, B, C, D = 1 << 4, 1 << 5, 1 << 6, 1 << 7
UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8
JUMP = UP
ATK = A | B | C | D
JUMPS = UP


def run_len(seq):
    if len(seq) == 0:
        return 0, 0
    n = 1
    total = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            total += 1
        else:
            n += 1
    return total, n


def metrics(seq, side):
    """side=0(P1 human) or 1(P2 model). 朝向: P1 前=RIGHT, P2 前=LEFT."""
    n = len(seq)
    if n == 0:
        return {}
    changes = sum(1 for i in range(1, n) if seq[i] != seq[i - 1])
    runs = 0
    for i in range(1, n):
        if seq[i] != seq[i - 1]:
            runs += 1
    fwd = RIGHT if side == 0 else LEFT
    back = LEFT if side == 0 else RIGHT
    atk = sum(1 for x in seq if int(x) & ATK)
    fw = sum(1 for x in seq if int(x) & fwd)
    bk = sum(1 for x in seq if int(x) & back)
    jmp = sum(1 for x in seq if int(x) & JUMP)
    return {'frames': n, 'decisions': changes,
            'duration_sec': round(n / 60.0, 2),
            'dec_per_sec': round(changes / max(1e-9, n / 60.0), 2),
            'macro_avg_frames': round(n / max(1, runs + 1), 2),
            'attack_rate': round(atk / n, 3),
            'approach_rate': round(fw / n, 3),
            'guard_retreat_rate': round(bk / n, 3),
            'jump_rate': round(jmp / n, 3)}


def react(seq_h, seq_m, side_m=1, window=12):
    """人类攻击起始→模型 12F 内后方向/dash/jump 反应."""
    n = min(len(seq_h), len(seq_m))
    starts = []
    prev = 0
    for i in range(n):
        a = int(seq_h[i]) & ATK
        if a and not (prev & ATK):
            starts.append(i)
        prev = int(seq_h[i])
    react_n = 0
    delays = []
    back = LEFT if side_m == 1 else RIGHT
    for s in starts:
        hit = None
        for j in range(s + 1, min(n, s + 1 + window)):
            x = int(seq_m[j])
            if (x & back) or (x & D) or (x & JUMP):
                hit = j - s
                break
        if hit is not None:
            react_n += 1
            delays.append(hit)
    return {'starts': len(starts), 'reacted': react_n,
            'react_rate': round(react_n / max(1, len(starts)), 3),
            'avg_delay': round(sum(delays) / max(1, len(delays)), 2)}


def main():
    # sessions -> rep names/model char
    sessions = {}
    for p in glob.glob(SESS):
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        reps = []
        for r in d.get('new_reps') or []:
            if isinstance(r, dict):
                rr = r.get('rep')
                if rr:
                    reps.append(rr)
            elif isinstance(r, str):
                reps.append(os.path.basename(r))
        sessions[os.path.basename(p)] = {
            'ts': d.get('ts'), 'char': d.get('char'),
            'human_wins': d.get('human_wins'), 'model_wins': d.get('model_wins'),
            'reps': reps,
            'detected': d.get('detected')}
    rep_paths = {}
    for dd in REP_DIRS:
        for p in glob.glob(os.path.join(dd, '*.rep')):
            rep_paths.setdefault(os.path.basename(p), p)
    res = {'sessions': sessions, 'reps': {}, 'by_char': {}, 'summary': {}}
    # 先按 session 映射; 未映射 rep 也全量统计(按 char)
    all_reps = sorted(rep_paths)
    for name in all_reps:
        p = rep_paths[name]
        try:
            r = parse_rep_file(p)
            arr = inputs_by_side(list(r.inputs))
            h = [int(x) for x in arr[:, 0]]
            m = [int(x) for x in arr[:, 1]]
            mm = metrics(m, 1)
            hm = metrics(h, 0)
            rk = react(h, m)
            ch = None
            try:
                ch = CHAR_LIBS.get(int(r.char_y), {}).get('name') or None
            except Exception:
                pass
            res['reps'][name] = {'char_y_id': getattr(r, 'char_y', None),
                                 'model': mm, 'human': hm, 'react': rk}
            key = str(getattr(r, 'char_y', '?'))
            agg = res['by_char'].setdefault(key, {'n': 0, 'model': {},
                                                  'human': {}, 'react': {}})
            agg['n'] += 1
        except Exception as e:
            res['reps'][name] = {'error': repr(e)[:100]}
    # aggregate averages
    def avg_metrics(kind):
        keys = ('dec_per_sec', 'macro_avg_frames', 'attack_rate',
                'approach_rate', 'guard_retreat_rate', 'jump_rate')
        vals = {k: [] for k in keys}
        for v in res['reps'].values():
            if kind in v:
                for k in keys:
                    vals[k].append(v[kind][k])
        return {k: round(sum(x) / max(1, len(x)), 3) for k, x in vals.items()}
    _rs = [v['react'] for v in res['reps'].values() if 'react' in v]
    _ra = {
        'react_rate': round(sum(x['react_rate'] for x in _rs)
                            / max(1, len(_rs)), 3),
        'avg_delay_frames': round(sum(x['avg_delay'] for x in _rs)
                                  / max(1, len(_rs)), 2),
        'threats': sum(x['starts'] for x in _rs),
        'reacted': sum(x['reacted'] for x in _rs)}
    res['summary'] = {'react_avg': _ra,
                      'n_reps': len([v for v in res['reps'].values()
                                     if 'model' in v]),
                      'model_avg': avg_metrics('model'),
                      'human_avg': avg_metrics('human')}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    # md
    s = res['summary']
    lines = ['# R19 历史行为指标（human vs model, rep 代理）', '',
             '- reps=%d；session=%d' % (s['n_reps'], len(sessions)),
             '', '| 指标 | 模型 | 人类 |', '|---|---|---|']
    for k in ('dec_per_sec', 'macro_avg_frames', 'attack_rate',
              'approach_rate', 'guard_retreat_rate', 'jump_rate'):
        lines.append('| %s | %s | %s |' % (k, s['model_avg'].get(k),
                                           s['human_avg'].get(k)))
    lines += ['', '## 受威胁反应（人类攻击后12F）',
              '- react_rate=%s avg_delay=%sF threats=%s reacted=%s' % (
                  _ra['react_rate'], _ra['avg_delay_frames'],
                  _ra['threats'], _ra['reacted']),
              '', '## 会话（历史）']
    for n, d in sorted(sessions.items()):
        lines.append('- %s char=%s 人%d-模型%d reps=%d' % (
            n, d.get('char'), d.get('human_wins') or 0,
            d.get('model_wins') or 0, len(d.get('reps') or [])))
    lines += ['', '说明：rep 无弹幕状态；擦弹/防御用"后方向/dash/jump 反应"代理；'
              '受威胁窗口=人类攻击起始后 12F。']
    open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps({'summary': res['summary'],
                      'sessions': len(sessions),
                      'reps': s['n_reps']}, ensure_ascii=False, indent=1))
    print('OUT', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
