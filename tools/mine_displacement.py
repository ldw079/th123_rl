# -*- coding: utf-8 -*-
"""CE-3(方案§可执行方案): 宏位移统计管线 — oracle分片窗口聚合。

产出 data/move_displacement_{char}.json: 逐action的自身位移+对手推板量
(命中/被防/空挥三桶分计)。低样本标low_confidence(不进特征)。

方法(方案§CE-3.1):
- 窗口: oracle分片上同一action ID连续出现区间
- Δ(own x/y): 窗口首末帧自身位置差
- Δ(opp x): 分桶(命中=comboDamage增 / 被防=opp action∈防御硬直集 /
  空挥=两者皆无)
- 宏→action映射复用reach_maps管线(宏末攻击步)

用法: python tools/mine_displacement.py [--char all]
"""
import argparse
import collections
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

# 防御硬直集(frame_events同源)
_GUARD_IDS = frozenset(range(150, 167)) - {158}
_MIN_SAMPLES = 5          # 低于此数标low_confidence
_WINDOW_PAD = 3           # 窗口前后padding帧


def mine_char(char_id, char_name, shards):
    """单角色位移统计。返回 {action_id: {...}} 字典。"""
    from bc_build import build_shard, LIBS, mirror_frames
    from bc_match import StreamMatcher

    name, lib = LIBS[char_id]
    matcher = StreamMatcher(lib, threshold=0.88)

    # 逐action聚合
    stats = collections.defaultdict(lambda: {
        'dx_self': [], 'dy_self': [],
        'dx_opp_hit': [], 'dx_opp_block': [], 'dx_opp_whiff': [],
        'n': 0,
    })

    for sp in shards:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if ilog is None or len(frames) < 100 or meta.get('err'):
            continue
        if meta['char_x'] != char_id and meta['char_y'] != char_id:
            continue

        for side in (0, 1):
            if side == 0 and meta['char_x'] != char_id:
                continue
            if side == 1 and meta['char_y'] != char_id:
                continue
            fr = frames if side == 0 else mirror_frames(frames)
            u16 = ilog[0] if side == 0 else mirror_input(ilog[1])

            # 逐帧扫描action窗口
            actions = [(i, f[0]['action']) for i, f in enumerate(fr)]
            i = 0
            while i < len(actions):
                fi, act = actions[i]
                if act < 300 or act > 598:    # 只看攻击/射击段
                    i += 1
                    continue
                # 找连续同action窗口
                j = i
                while j < len(actions) and actions[j][1] == act:
                    j += 1
                w_start = max(0, fi - _WINDOW_PAD)
                w_end = min(len(fr), j + _WINDOW_PAD)

                own_s = fr[w_start][0]
                own_e = fr[w_end - 1][0]
                opp_s = fr[w_start][1]
                opp_e = fr[w_end - 1][1]

                dx_self = own_e['position.x'] - own_s['position.x']
                dy_self = own_e['position.y'] - own_s['position.y']
                dx_opp = opp_e['position.x'] - opp_s['position.x']

                # 分桶判定
                combo_s = own_s.get('comboDamage', 0) or 0
                combo_e = own_e.get('comboDamage', 0) or 0
                opp_act_e = opp_e.get('action', 0)

                if combo_e > combo_s:
                    stats[act]['dx_opp_hit'].append(dx_opp)
                elif opp_act_e in _GUARD_IDS:
                    stats[act]['dx_opp_block'].append(dx_opp)
                else:
                    stats[act]['dx_opp_whiff'].append(dx_opp)

                stats[act]['dx_self'].append(dx_self)
                stats[act]['dy_self'].append(dy_self)
                stats[act]['n'] += 1
                i = j

    # 汇总输出
    out = {}
    for act, s in sorted(stats.items()):
        if s['n'] < _MIN_SAMPLES:
            continue
        def _agg(vals):
            if not vals:
                return None
            arr = np.array(vals)
            return {'mean': round(float(arr.mean()), 1),
                    'std': round(float(arr.std()), 1),
                    'n': len(arr)}
        rec = {
            'n_windows': s['n'],
            'dx_self': _agg(s['dx_self']),
            'dy_self': _agg(s['dy_self']),
            'dx_opp_hit': _agg(s['dx_opp_hit']),
            'dx_opp_block': _agg(s['dx_opp_block']),
            'dx_opp_whiff': _agg(s['dx_opp_whiff']),
            'low_confidence': s['n'] < _MIN_SAMPLES * 4,
        }
        out[str(act)] = rec
    return out


def mirror_input(u16):
    """右方输入→左方镜像(bc_build同源)。"""
    return u16


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='all',
                    help='角色名或all(三主力)')
    ap.add_argument('--shards', type=int, default=0,
                    help='最大分片数(0=全部)')
    a = ap.parse_args()

    from bc_build import LIBS
    # tr*分片优先(带ilog; 同bc_build策略 — 旧格式无ilog被过滤后=空)
    shards_all = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))
    shards_all += [p for p in sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', '*.npz')))
        if not os.path.basename(p).startswith('tr')]
    if a.shards:
        shards_all = shards_all[:a.shards]

    targets = {'reimu': 0, 'marisa': 1, 'suika': 9} if a.char == 'all' \
        else {a.char: next((cid for cid, (n, _) in LIBS.items()
                            if n == a.char), None)}
    targets = {k: v for k, v in targets.items() if v is not None}

    for cname, cid in targets.items():
        print('[%s] 挖掘位移(%d分片)...' % (cname, len(shards_all)))
        result = mine_char(cid, cname, shards_all)
        dst = os.path.join(ROOT, 'data',
                           'move_displacement_%s.json' % cname)
        payload = {
            'source': 'oracle_v2 shards, tools/mine_displacement.py',
            'char': cname,
            'min_samples': _MIN_SAMPLES,
            'total_actions': len(result),
            'high_confidence': sum(1 for v in result.values()
                                   if not v['low_confidence']),
            'actions': result,
        }
        tmp = dst + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dst)
        print('  → %s (%d actions, %d高置信)' % (
            dst, len(result), payload['high_confidence']))


if __name__ == '__main__':
    main()
