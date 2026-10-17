# -*- coding: utf-8 -*-
"""位置分桶连段挖掘器(R23): 从oracle_v2原始帧+输入提取
"命中确认后的专家输入路线", 按位置分桶(版边/空中/中央)聚合。
方法(全部实测数据, R4合规):
- 命中事件: 对手HP下降帧; 回溯到我方攻击起手(按住攻击键/攻击动作的起点)
- 路线: 起手→+90帧内我方输入序列, 解码u16→(键组, 帧数)步, 归一化聚合
- 分桶: 命中瞬间对手贴角(x<120/>1120)/浮空/其它(中央)
- 结局: 路线内对手总掉血(出伤质量) + 对手防御帧数(压制质量)
用法: python tools/combo_mine_positional.py [char] [max_shards]"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')
from bc_build import build_shard, mirror_frames, CS_SIZE  # noqa: E402

SHARDS = sorted(glob.glob(
    os.path.expandvars(r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle_v2\shards\*.npz')))
CHAR_IDS = {'reimu': 0, 'marisa': 1, 'suika': 9}
GUARD_IDS = set(range(150, 168))
HOR = {0: (), 1: ('right',), 3: ('left',)}   # u>>6&3
VER = {0: (), 1: ('up',), 3: ('down',)}      # u>>8&3


def decode(u):
    ks = set(HOR.get((u >> 6) & 3, ())) | set(VER.get((u >> 8) & 3, ()))
    for bit, name in ((1, 'A'), (2, 'B'), (4, 'C'), (8, 'D')):
        if u & bit:
            ks.add(name)
    return tuple(sorted(ks))


def steps_of(inputs, i0, i1):
    """[i0,i1)输入 → 归一化(键组,帧数)步列表; 去首尾空步, 合并同键。"""
    raw = []
    for j in range(max(0, i0), i1):
        k = decode(int(inputs[j]))
        if raw and raw[-1][0] == k:
            raw[-1][1] += 1
        else:
            raw.append([k, 1])
    while raw and not raw[0][0]:
        raw.pop(0)
    while raw and not raw[-1][0]:
        raw.pop()
    return [(k, n) for k, n in raw if n >= 1]


def bucket_frames(n):
    for b in (2, 4, 6, 8, 12, 99):
        if n <= b:
            return b
    return 99


def sig(steps):
    return tuple((k, bucket_frames(n)) for k, n in steps)


def mine(char, max_shards=80):
    cid = CHAR_IDS[char]
    routes = defaultdict(lambda: [0, 0.0, 0.0, 0])  # sig→[次数, 总伤害, 总防帧, 总帧]
    n_sh = 0
    for sp in SHARDS[:max_shards * 2]:
        if n_sh >= max_shards:
            break
        try:
            meta, frames, inputs = build_shard(sp)
        except Exception:
            continue
        if inputs.ndim != 2 or len(inputs) < 200 or len(frames) < 200:
            continue
        if meta['char_x'] != cid and meta['char_y'] != cid:
            continue
        n_sh += 1
        for side in (0, 1):
            if side == 0:
                if meta['char_x'] != cid:
                    continue
                fr, u16 = frames, inputs[:, 1]
                me_idx, opp_idx = 0, 1
            else:
                if meta['char_y'] != cid:
                    continue
                fr, u16 = mirror_frames(frames, inputs)
                me_idx, opp_idx = 0, 1
            n = min(len(fr), len(u16))
            for i in range(1, n - 1):
                me, opp = fr[i][me_idx], fr[i][opp_idx]
                opp_prev = fr[i - 1][opp_idx]
                dmg = opp_prev['hp'] - opp['hp']
                if dmg <= 0:
                    continue
                # 分桶(命中瞬间, 我方视角)
                oox = opp['position.x']
                if oox < 120 or oox > 1120:
                    bk = 'corner'
                elif opp['airBorne']:
                    bk = 'air'
                else:
                    bk = 'mid'
                # 回溯起手: 连续按攻击键/攻击动作的最早点(≤40帧)
                s = i
                for j in range(i, max(0, i - 40), -1):
                    k = decode(int(u16[j])) if j < len(u16) else ()
                    act = fr[j][me_idx].get('action', 0) or 0
                    if any(b in k for b in 'ABCD') or 230 <= act < 600:
                        s = j
                    else:
                        break
                # 前向: 命中后≤50帧; 首个≥10帧"无攻击键"间隙=连段结束
                end = min(n - 1, i + 50)
                last_atk = i
                gap = 0
                for j in range(i, end):
                    o = fr[j][opp_idx]
                    if o['hp'] < fr[j - 1][opp_idx]['hp']:
                        last_atk = j
                    k = decode(int(u16[j])) if j < len(u16) else ()
                    if any(b in k for b in 'ABCD'):
                        gap = 0
                    else:
                        gap += 1
                        if gap >= 10:
                            end = j - 9
                            break
                    if (o.get('action', 0) or 0) < 100 \
                            and j - last_atk > 15 and j > i + 8:
                        end = j
                        break
                if end <= s:
                    continue
                # 路线=起手尾2步(命中前的攻击按入)+命中后跟进
                # (整段pre-hit会混入中性移动噪音, 只留贴近命中的起手)
                pre = steps_of(u16, s, i + 1)
                post = steps_of(u16, i + 1, end)
                steps = (pre[-2:] if len(pre) > 2 else pre) + post
                if not steps or len(steps) > 10:
                    continue
                tot = fr[s][opp_idx]['hp'] - fr[end - 1][opp_idx]['hp']
                if tot < 150:      # <150伤害不算出伤/压制路线
                    continue
                gframes = sum(1 for j in range(s, end)
                              if (fr[j][opp_idx].get('action', 0) or 0)
                              in GUARD_IDS)
                r = routes[(bk, sig(steps))]
                r[0] += 1
                r[1] += tot
                r[2] += gframes
                r[3] += end - s
    return routes, n_sh


def fmt(steps):
    out = []
    for k, n in steps:
        name = '+'.join(k) if k else 'idle'
        out.append('%s(%dF)' % (name, n))
    return ' > '.join(out)[:150]


def main():
    chars = sys.argv[1:2] or ['all']
    mx = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    for ch in (['reimu', 'marisa', 'suika'] if chars == ['all'] else chars):
        routes, n_sh = mine(ch, mx)
        print('==== %s (%d分片, %d条路线) ====' % (ch, n_sh, len(routes)))
        for bk in ('corner', 'air', 'mid'):
            sub = {k[1]: v for k, v in routes.items() if k[0] == bk}
            top = sorted(sub.items(), key=lambda kv: -kv[1][0])[:6]
            print('-- [%s] %d种路线, 高频Top:' % (bk, len(sub)))
            for sg, (cnt, dmg, gf, fr) in top:
                print('   %3d次 均伤%4.0f 防帧%3.0f | %s'
                      % (cnt, dmg / cnt, gf / cnt, fmt(sg)))
        print()


if __name__ == '__main__':
    main()
