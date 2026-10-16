# -*- coding: utf-8 -*-
"""CH-0 蓄力语义探针(蓄力攻击支持方案2026-10-14, 全方案的门).

在oracle分片上离线回答:
  Q1 蓄力期签名: 同键连续按压≥25帧窗口内 pose/poseFrame/action 是否
     呈稳定可分模式(对照: 普通8-12帧按压窗口)?
  Q2 放出后可分性: 松键后窗口的 action/pose 与普通版差异?
  Q3 阈值分布: 按压时长→出招形态边界。

产出: docs/_reviews/charge_semantics_probe_2026-10-14.md(签名查表数据)。
门规则: Q1无可用签名 → 观测侧(CH-1)不施工, 如实记录结构性盲区。
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')

from bc_build import build_shard   # noqa: E402

BITS = {'A': 0x10, 'B': 0x20, 'C': 0x40, 'D': 0x80}
HOLD_MIN = 25        # 蓄力候选窗(≥25帧同键保持)
CTRL_MIN = 8         # 普通按压对照窗(8-12帧)


def hold_windows(u, key):
    """同键连续按压窗口 [(start, end), ...](end-exclusive)."""
    p = (np.asarray(u, dtype=np.uint16) & BITS[key]) != 0
    d = np.diff(p.astype(int))
    starts = (np.flatnonzero(d == 1) + 1).tolist()
    ends = (np.flatnonzero(d == -1) + 1).tolist()
    if p[0]:
        starts = [0] + starts
    if p[-1]:
        ends = ends + [len(p)]
    return list(zip(starts, ends))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=200)
    ap.add_argument('--out', default=os.path.join(
        ROOT, 'docs', '_reviews', 'charge_semantics_probe_2026-10-14.md'))
    a = ap.parse_args()
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:a.limit]

    # 收集: 长按窗(蓄力候选)与对照窗(普通按压)的逐帧(action,pose,poseFrame)
    long_traces = []      # {char_id, key, dur, act_seq, pose_seq, poseF_seq, after}
    ctrl_traces = []
    n_windows = collections.Counter()
    for sp in shards:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if ilog is None or len(frames) < 200:
            continue
        for side in (0, 1):
            cid = meta['char_x'] if side == 0 else meta['char_y']
            u = ilog[0] if side == 0 else ilog[1]
            st = frames        # 左侧视角; 右侧镜像帧的pose语义同(姿态不自镜像翻转值)
            me = 0 if side == 0 else 1
            for key in ('B', 'C', 'A'):
                for s0, e0 in hold_windows(u, key):
                    dur = e0 - s0
                    if dur >= HOLD_MIN:
                        n_windows[('long', key)] += 1
                        seg = st[s0:e0]
                        after = st[e0:min(e0 + 20, len(st))]
                        long_traces.append({
                            'char': cid, 'key': key, 'dur': int(dur),
                            'act': [f[me].get('action', 0) for f in seg[::4]],
                            'pose': [f[me].get('pose', 0) for f in seg[::4]],
                            'poseF': [f[me].get('poseFrame', 0)
                                      for f in seg[::4]],
                            'after_act': [f[me].get('action', 0)
                                          for f in after[::4]],
                            'after_pose': [f[me].get('pose', 0)
                                           for f in after[::4]],
                        })
                    elif CTRL_MIN <= dur <= 12:
                        n_windows[('ctrl', key)] += 1
                        if len(ctrl_traces) < 600:
                            seg = st[s0:e0]
                            ctrl_traces.append({
                                'char': cid, 'key': key, 'dur': int(dur),
                                'pose': [f[me].get('pose', 0)
                                         for f in seg[::4]],
                            })
    # ---- Q1: 签名分析 ----
    lines = ['# CH-0 蓄力语义探针(2026-10-14)', '',
             '数据: %d shards, 长按窗(≥%d帧) %s, 对照窗(8-12帧) %s'
             % (len(shards), HOLD_MIN,
                {k: n_windows[('long', k)] for k in 'BCA'},
                {k: n_windows[('ctrl', k)] for k in 'BCA'}), '']
    lines.append('长按窗总数: %d (对照窗采样%d)'
                 % (len(long_traces), len(ctrl_traces)))
    if long_traces:
        lines.append('')
        lines.append('## Q1 蓄力期签名(逐角色×键: 按压期pose众数/占比)')
        sig = collections.defaultdict(list)
        for t in long_traces:
            sig[(t['char'], t['key'])].append(t)
        rows = []
        for (cid, key), ts in sorted(sig.items()):
            pose_all = [p for t in ts for p in t['pose']]
            if not pose_all:
                continue
            mc = collections.Counter(pose_all).most_common(3)
            dom, cnt = mc[0]
            rows.append((cid, key, len(ts), dom, cnt / len(pose_all),
                         sorted(set(pose_all))[:8]))
        for cid, key, n, dom, frac, uniq in rows:
            lines.append('- char%d ×%s: %d窗 | pose众数=%d(%.0f%%) '
                         'distinct=%s' % (cid, key, n, dom, frac * 100,
                                          uniq))
        # 对照组pose基线
        ctrl_pose = collections.Counter(
            p for t in ctrl_traces for p in t['pose'])
        lines.append('')
        lines.append('对照组(普通按压)pose分布Top5: %s'
                     % ctrl_pose.most_common(5))
        # 签名可分性: 长按窗dom-pose与对照dom-pose差异
        if ctrl_pose:
            ctrl_dom = ctrl_pose.most_common(1)[0][0]
            sep = [r for r in rows if r[3] != ctrl_dom]
            lines.append('')
            lines.append('**Q1判定**: %d/%d个(角色×键)组的长按pose众数'
                         '≠对照众数(%d)' % (len(sep), len(rows), ctrl_dom))
        # ---- Q2: 放出后 ----
        lines.append('')
        lines.append('## Q2 放出后(松键后20帧)action样本')
        q2 = collections.defaultdict(collections.Counter)
        for t in long_traces:
            for a_ in t['after_act'][:3]:
                q2[(t['char'], t['key'])][a_] += 1
        for (cid, key), c in sorted(q2.items())[:12]:
            lines.append('- char%d ×%s 松键后action Top: %s'
                         % (cid, key, c.most_common(4)))
        # ---- Q3: 时长分布 ----
        lines.append('')
        lines.append('## Q3 长按时长分布')
        durs = [t['dur'] for t in long_traces]
        lines.append('min=%d p25=%d 中位=%d p75=%d max=%d'
                     % (min(durs), np.percentile(durs, 25),
                        np.median(durs), np.percentile(durs, 75),
                        max(durs)))
        hist = collections.Counter(
            (d // 10) * 10 for d in durs)
        lines.append('分桶(10帧): %s' % sorted(hist.items()))
        # 原始数据落盘供CH-1查表
        jout = a.out.replace('.md', '_data.json')
        with open(jout, 'w', encoding='utf8') as f:
            json.dump({'long': long_traces,
                       'ctrl_pose': dict(ctrl_pose)}, f,
                      ensure_ascii=False)
        lines.append('')
        lines.append('原始窗口数据: %s' % jout)
    else:
        lines.append('')
        lines.append('**Q1判定: 无长按窗样本** — 本语料蓄力行为稀少, '
                     '观测签名无法建立(结构性数据不足, 如实记录)。')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('\n报告: %s' % a.out)


if __name__ == '__main__':
    main()
