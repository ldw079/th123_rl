# -*- coding: utf-8 -*-
"""S-5(合并终版方案第一波): 专家shard的punish后处理.

对oracle_v2 shard双边逐帧重放S-1 MyPunishTracker(与在线同一实现)
→ 每个匹配宏的(类别, 结果) + 当时各类punish率快照 →
sidecar文件 data/oracle_v2/punish/{shard}.npz(不动原shard —
无EP_SCHEMA冲击, 回滚=删目录)。bc_build的S-2接线(维7-10)后续消费。

用法: python tools/expert_punish_track.py [--limit 3]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from bc_build import build_shard, mirror_frames, mirror_input  # noqa: E402
from bc_match import StreamMatcher                          # noqa: E402
from my_punish_tracker import MyPunishTracker, classify     # noqa: E402
from train_tm import CHAR_LIBS                              # noqa: E402
from action_tables import (reimu_ATTACK_IDS, reimu_SHOT_IDS,   # noqa: E402
                           marisa_ATTACK_IDS, marisa_SHOT_IDS,
                           suika_ATTACK_IDS, suika_SHOT_IDS)

_OPP_ATK = {
    0: reimu_ATTACK_IDS | reimu_SHOT_IDS,
    1: marisa_ATTACK_IDS | marisa_SHOT_IDS,
    9: suika_ATTACK_IDS | suika_SHOT_IDS,
}
_ALL_ATK = frozenset().union(*_OPP_ATK.values())
_GUARD_STUN = frozenset(range(150, 167)) - {158}
_CLASS_ORDER = ('JUMP', 'MELEE', 'BULLET', 'SKILL', 'GUARD_PREP', 'OTHER')
OUT_DIR = os.path.join(ROOT, 'data', 'oracle_v2', 'punish')


def track_side(frames, u16, macros, char_name, opp_cid):
    """单边重放: 匹配宏窗口内逐帧喂S-1 tracker。

    d_take/d_deal=HP逐帧差分; 对手攻击态查action表(池外用并集);
    blocked=我方入GUARD_STUN。宏结束→end()(EMA)→快照一行。
    返回(帧号, 类别id, 结果, 6类rate快照)四数组。
    """
    matcher = StreamMatcher(macros, threshold=0.88)
    facings = [1 if f[0]['direction'] > 0 else -1 for f in frames]
    hits = matcher.walk(u16, facings)
    names = [m[0] for m in macros]
    lib = CHAR_LIBS[char_name]
    cls_ids = {c: i for i, c in enumerate(_CLASS_ORDER)}
    atk = _OPP_ATK.get(opp_cid, _ALL_ATK)
    tracker = MyPunishTracker()
    rows_f, rows_cls, rows_out, rows_rate = [], [], [], []
    prev_my = frames[0][0].get('hp', 10000)
    prev_opp = frames[0][1].get('hp', 10000)
    for k, (hf, hidx, _conf) in enumerate(hits):
        end = hits[k + 1][0] if k + 1 < len(hits) else len(frames)
        name = names[hidx]
        cls = classify(name, lib)
        # P1-7①(从零#4): rate快照移到begin前 — 决策时点的**先验率**
        # (不含本宏自身结局)。原版在end()后快照=帧f特征已含f的未来
        # (bc锚未来信息泄漏); 在线特征同为先验, 离线对齐在线语义。
        pre_rate = [float(tracker.punish_rate(c)) for c in _CLASS_ORDER]
        tracker.begin(cls)
        for i in range(hf, min(end, len(frames))):
            left, right = frames[i][0], frames[i][1]
            d_take = max(0, prev_my - left.get('hp', prev_my))
            d_deal = max(0, prev_opp - right.get('hp', prev_opp))
            prev_my = left.get('hp', prev_my)
            prev_opp = right.get('hp', prev_opp)
            tracker.frame(d_take, right.get('action', 0) in atk,
                          d_deal, left.get('action', 0) in _GUARD_STUN)
        outcome = tracker.end()
        rows_f.append(hf)
        rows_cls.append(cls_ids[cls])
        rows_out.append(-1 if outcome is None else outcome)
        rows_rate.append(pre_rate)
    return (np.array(rows_f, dtype=np.int32),
            np.array(rows_cls, dtype=np.int8),
            np.array(rows_out, dtype=np.int8),
            np.array(rows_rate, dtype=np.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', default=OUT_DIR)
    ap.add_argument('--part', default='',
                    help='i/k 三路分片加速(如 0/3) — 按序取第i片')
    a = ap.parse_args()
    from bc_build import LIBS
    # tr*分片优先(带ilog精确对齐 — S-5规格: 无ilog走置信度门=暂缓)
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))
    shards += sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', '*.npz')))
    _seen = set()
    shards = [s for s in shards if not (s in _seen or _seen.add(s))]
    if a.part:
        _i, _k = (int(x) for x in a.part.split('/'))
        shards = [s for j, s in enumerate(shards) if j % _k == _i]
        print('[part %s] 本片分片数: %d' % (a.part, len(shards)))
    if a.limit:
        shards = shards[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    n_done = n_skip = 0
    for sp in shards:
        out_p = os.path.join(a.out, os.path.basename(sp))
        if os.path.exists(out_p):
            continue
        try:
            meta, frames, inputs, ilog = build_shard(sp)
            if ilog is None or len(frames) < 100 or meta.get('err'):
                n_skip += 1
                continue
            sides = {}
            for side in (0, 1):
                cid = meta['char_x'] if side == 0 else meta['char_y']
                if side == 0:
                    fr, u16, opp = frames, ilog[0], meta['char_y']
                else:
                    fr = mirror_frames(frames)
                    u16 = mirror_input(ilog[1])
                    opp = meta['char_x']
                char_name, macros = LIBS[cid]
                f_, c_, o_, r_ = track_side(fr, u16, macros,
                                            char_name, opp)
                sides['%d_f' % side] = f_
                sides['%d_cls' % side] = c_
                sides['%d_out' % side] = o_
                sides['%d_rate' % side] = r_
            sides['meta'] = np.array(json.dumps(
                {'src': os.path.basename(sp), 'schema': 'punish_v1'}))
            tmp = out_p + '.tmp.npz'
            np.savez(tmp, **sides)
            os.replace(tmp, out_p)
            n_done += 1
            if n_done % 20 == 0:
                print('  %d sidecars (跳过%d)' % (n_done, n_skip))
        except Exception as e:
            n_skip += 1
            print('  [跳过] %s: %s' % (os.path.basename(sp), e))
    print('S-5后处理完成: %d sidecars (跳过%d) → %s'
          % (n_done, n_skip, a.out))


if __name__ == '__main__':
    main()
