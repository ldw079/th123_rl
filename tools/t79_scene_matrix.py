# -*- coding: utf-8 -*-
"""task-79 场景矩阵草稿: 3 角色×15 起手×5 对手状态×4 位置×3 reps = 2700."""
import json
import os
import sys

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
from train_tm import CHAR_LIBS  # noqa: E402

OUT = r'D:\temp\t79_scene_matrix_draft_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\t79_scene_matrix_draft_20261027.md'
CHARS = ('reimu', 'marisa', 'suika')
STATES = ('standing', 'crouch', 'air', 'ukemi', 'guard')
POS = ('near', 'mid', 'far', 'corner')
REPS = 3


def starters(ch):
    names = [m[0] for m in CHAR_LIBS[ch]['macros']]
    pref = [n for n in names if any(k in n for k in
            ('连', '压', '择', '起', 'A', 'B', 'C'))]
    # 稳定取 15 个不同起手
    out = []
    for n in pref:
        if n not in out:
            out.append(n)
        if len(out) >= 15:
            break
    return out


def main():
    rows = []
    for ch in CHARS:
        st = starters(ch)
        for s in st:
            for state in STATES:
                for pos in POS:
                    for rep in range(1, REPS + 1):
                        rows.append({
                            'id': len(rows), 'char': ch, 'starter': s,
                            'opp_state': state, 'position': pos, 'rep': rep,
                            'weather': 'any', 'cards': 'any',
                            'replay_required': 3})
    res = {'chars': CHARS, 'starters_per_char': 15,
           'states': STATES, 'positions': POS, 'reps': REPS,
           'rows': len(rows), 'data': rows}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    lines = ['# task-79 场景矩阵草稿（2700 用例）', '',
             '- 3 角色 × 15 起手 × 5 对手状态 × 4 位置 × 3 reps = **%d**' % len(rows),
             '- 字段：char/starter/opp_state/position/rep/weather/cards/replay_required',
             '- 来源：CHAR_LIBS 宏名（连/压/择/起手）自动抽取；矩阵为**草稿**，'
             'trailmod oracle 源待纳管后补充。', '',
             '| 角色 | 起手数 | 状态 | 位置 | reps |', '|---|---|---|---|---|']
    for ch in CHARS:
        lines.append('| %s | 15 | 5 | 4 | 3 |' % ch)
    lines += ['', '数据：`D:\\temp\\t79_scene_matrix_draft_20261027.json`']
    open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('rows', len(rows), 'out', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
