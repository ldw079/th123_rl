# -*- coding: utf-8 -*-
"""按钮签名→move id 实测映射挖掘(R24): oracle帧流里, 动作跳入攻击/射击
move的瞬间, 记录此前按住的(按钮,前向,纵向)签名 → 投票。
产出 data/move_hints_<char>.json — reach_maps.py用它把宏(脚本末攻击步)
解析到move id → XML射程。
用法: python tools/mine_input_moves.py [max_shards]"""
import glob
import json
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')
from bc_build import build_shard, mirror_frames  # noqa: E402
from action_tables import CHAR_ACTION_TABLES as T  # noqa: E402

SHARDS = sorted(glob.glob(
    r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle_v2\shards\*.npz'))
CHAR_IDS = {'reimu': 0, 'marisa': 1, 'suika': 9}
OUT = r'%USERPROFILE%\Desktop\workplace\th123_rl\data'


def sig_of(u):
    """u16 → (按钮串, 前向0/1, 纵向-1/0/1)。前向=H&3==1(右, 己视角)。
    H/V的2是罕见编码(斜向过渡) — 按无方向处理。"""
    btns = ''.join(sorted(n for b, n in ((1, 'A'), (2, 'B'), (4, 'C'),
                                         (8, 'D')) if u & b))
    h = 1 if (u >> 6) & 3 == 1 else 0
    v = {0: 0, 1: 1, 2: 0, 3: -1}[(u >> 8) & 3]
    return '%s|%d|%d' % (btns, h, v)


def main():
    mx = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    votes = {ch: Counter() for ch in CHAR_IDS}   # (sig, move) → n
    atk_all = {ch: T[ch]['attack'] | T[ch]['shot'] for ch in CHAR_IDS}
    n_sh = 0
    for sp in SHARDS[:mx * 2]:
        if n_sh >= mx:
            break
        try:
            meta, frames, inputs = build_shard(sp)
        except Exception:
            continue
        if inputs.ndim != 2 or len(inputs) < 200:
            continue
        if meta['char_x'] not in CHAR_IDS.values() \
                and meta['char_y'] not in CHAR_IDS.values():
            continue
        n_sh += 1
        for side in (0, 1):
            cx = meta['char_x'] if side == 0 else meta['char_y']
            ch = [k for k, v in CHAR_IDS.items() if v == cx]
            if not ch:
                continue
            ch = ch[0]
            if side == 0:
                fr, u16 = frames, inputs[:, 1]
            else:
                fr, u16 = mirror_frames(frames, inputs)
            n = min(len(fr), len(u16))
            # 按键上升沿锚定: A/B/C/D从未按→按的帧j, 向前20帧等
            # 动作首次落入攻击/射击集(起手输入早于动作ID出现, i-1
            # 关联全是噪声 — 306霸屏教训)
            for j in range(2, n - 20):
                uj, uj1 = int(u16[j]), int(u16[j - 1])
                pressed = uj & 0xF
                if not pressed or (uj1 & 0xF):
                    continue        # 非上升沿
                s = sig_of(uj)
                for k in range(j, j + 20):
                    a = fr[k][0].get('action', 0) or 0
                    a0 = fr[k - 1][0].get('action', 0) or 0
                    if a in atk_all[ch] and a0 not in atk_all[ch]:
                        # 持续≥2帧才算真动作(滤转场单帧噪声)
                        a2 = fr[k + 1][0].get('action', 0) or 0 \
                            if k + 1 < n else 0
                        if a2 == a:
                            votes[ch][(s, a)] += 1
                        break
    for ch in CHAR_IDS:
        best = {}
        for (s, a), n in votes[ch].items():
            if n >= 3 and n > best.get(s, (None, 0))[1]:
                best[s] = (a, n)
        out = {s: a for s, (a, n) in best.items()}
        p = os.path.join(OUT, 'move_hints_%s.json' % ch)
        json.dump(out, open(p, 'w'), ensure_ascii=False, indent=1)
        print('%s: %d个签名 → %s' % (ch, len(out), os.path.basename(p)))
        for s, a in sorted(out.items())[:14]:
            print('   %-10s → move %d (reach %s)'
                  % (s, a, T[ch]['reach'].get(a, '-')))


if __name__ == '__main__':
    main()
