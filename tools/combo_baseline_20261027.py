# -*- coding: utf-8 -*-
"""task-62/连段断点 基线(proxy): 从 episodes 计算 选择率/宏帧长/类别分布.

完成率/confirm/gate_truncate/hit 打断当前无逐决策遥测(缺口如实记录);
lab 真值(88 trailmod/50 lab)严格 replay 需隔离 lab, 本轮 pending。
输出 D:\\temp\\combo_baseline_20261027.json + md
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
from train_tm import CHAR_LIBS  # noqa: E402

OUT = r'D:\temp\combo_baseline_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\combo_baseline_20261027.md'
BASE = r'D:\temp\th123_models\fleet\episodes_keep'


def cat(name):
    for k in ('连段', '连', '压制', '压', '择', '崩', '爆'):
        if k in name:
            return 'combo_pressure'
    for k in ('防御', '立防', '蹲防', '受身', '起身', '结界'):
        if k in name:
            return 'defense'
    for k in ('前进', '前冲', '空翔前', '前跳', '飞翔'):
        if k in name:
            return 'approach'
    return 'poke_misc'


def main():
    res = {'chars': {}, 'note': ('选择率/宏帧长=episodes 实测; 完成率/confirm_timeout/'
                                 'gate_truncate/hit打断=无逐决策遥测, 需 task-62 仪表; '
                                 'lab 88 trial 严格 replay=隔离 lab pending')}
    for ch in ('reimu', 'marisa', 'suika'):
        names = [m[0] for m in CHAR_LIBS[ch]['macros']]
        files = glob.glob(os.path.join(BASE, ch, '*.npz'))
        cnt = Counter()
        combos = Counter()
        dec = 0
        run_frames = []
        for p in files:
            try:
                z = np.load(p, allow_pickle=True)
                A = np.asarray(z['acts'], np.int64)
            except Exception:
                continue
            dec += len(A)
            run = 1
            for i, a in enumerate(A):
                if 0 <= a < len(names):
                    nm = names[a]
                    cnt[cat(nm)] += 1
                    if cat(nm) == 'combo_pressure':
                        combos[nm] += 1
                if i and a == A[i - 1]:
                    run += 1
                else:
                    if i:
                        run_frames.append(run)
                    run = 1
        if dec:
            res['chars'][ch] = {
                'episodes': len(files), 'decisions': dec,
                'cat_rate': {k: round(v / dec, 3) for k, v in cnt.items()},
                'combo_choice_rate': round(cnt['combo_pressure'] / dec, 3),
                'macro_avg_frames': round(
                    sum(run_frames) / max(1, len(run_frames)), 2),
                'top_combos': combos.most_common(10)}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    lines = ['# 连段/断点 基线（proxy，2026-10-27）', '',
             '- 数据: episodes_keep（120/char 裁剪后训练期新片段）',
             '- **缺口**：完成率/confirm_timeout/gate_truncate/hit 打断 无逐决策遥测；'
             '需 task-62 仪表（下一步）',
             '- lab 88 trailmod/50 lab 严格 replay：deferred（隔离 lab）', '',
             '| 角色 | 局数 | 决策 | combo选择率 | 宏平均帧 | 类别分布 |',
             '|---|---|---|---|---|---|']
    for ch, d in res['chars'].items():
        lines.append('| %s | %d | %d | %s | %s | %s |' % (
            ch, d['episodes'], d['decisions'], d['combo_choice_rate'],
            d['macro_avg_frames'],
            ', '.join('%s=%s' % (k, v) for k, v in d['cat_rate'].items())))
    lines += ['', '## top combo 宏（选择次数）']
    for ch, d in res['chars'].items():
        lines.append('- %s: %s' % (ch, d['top_combos'][:5]))
    open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps(res, ensure_ascii=False)[:1200])
    return 0


if __name__ == '__main__':
    sys.exit(main())
