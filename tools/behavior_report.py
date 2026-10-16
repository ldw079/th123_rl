# -*- coding: utf-8 -*-
"""BH-1(行为健康方案v4): 行为健康报告 — 把"感觉"变成曲线的数据源。

八表(方案§BH-1):
  2 进攻积极性: 承诺动作占比(攻击/连段类决策份额)
  3 连段完成率: 选连段宏→命中结算%(被打断/被防/落空分解)
  4 续打率: 我方命中→下一决策选攻击类%(vs 未命中时的基准)
  5 对位连段成功率: 完成率按对手角色分解(对位盲直接测量)
  6 位移混乱度: 方向翻转率+速度自相关(帧日志)
  7 反应延迟: 事件→下一决策帧距分布(帧日志; FrameEventDetector离线重放)
  8 防守错位矩阵: 我方防姿×对手来袭段位(帧日志+guard_height逐角色表)
  (表1纵向标尺=COM阶梯, 独立工具com_ladder_report, 低载窗口跑)

数据源: fleet/episodes/bh_*.json旁车(表2-5) + STORE/frame_logs/*.pkl
(表6-8, 需TH123_FRAME_LOG=1). 全只读; 顺手修剪旁车超量(保最近1000/角色)。

用法: python tools/behavior_report.py [--char reimu] [--last 200]
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
EP_DIR = os.path.join(STORE, 'fleet', 'episodes')
FL_DIR = os.path.join(STORE, 'frame_logs')


def prune_sidecars(char, keep=1000):
    files = sorted(glob.glob(os.path.join(EP_DIR, 'bh_%s_*.json' % char)),
                   key=lambda p: (os.path.getmtime(p), p))
    for p in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(p)
        except OSError:
            pass
    return len(files)


def tables_2to5(char, last_n):
    from behavior_health import aggregate, rates
    agg = aggregate(EP_DIR, char, last_n)
    r = rates(agg)
    print('═' * 62)
    print(' 行为健康报告 %s (旁车%d份, 决策%d)' % (char, r['files'],
                                              r['decisions']))
    print('═' * 62)
    if r['files'] == 0:
        print(' (无旁车数据 — fleet重启后首局起累积)')
        return
    print('[表2] 进攻积极性')
    print('  承诺动作占比(攻击/连段类): %.1f%%' % (100 * r['commit_rate']))
    print('[表3] 连段完成率 (n=%d)' % r['combo_total'])
    if r['combo_total']:
        print('  命中结算 %.1f%% | 打断 %.1f%%'
              % (100 * r['combo_hit_rate'],
                 100 * r['combo_interrupt_rate']))
    print('[表4] 续打率')
    print('  命中后续打 %.1f%% | 未命中时攻击率 %.1f%% (差值=承诺倾向)'
          % (100 * r['followup_hit'], 100 * r['followup_nohit']))
    print('[表5] 对位连段成功率')
    if r['combo_by_opp']:
        for oc, d in sorted(r['combo_by_opp'].items(),
                            key=lambda kv: -kv[1]['n']):
            print('  vs %-10s n=%-4d 命中率 %.1f%%'
                  % (oc, d['n'], 100 * d['hit_rate']))
    else:
        print('  (尚无连段类决策)')
    if r['trans_top']:
        print('[宏转移Top]')
        for k, v in list(r['trans_top'].items())[:8]:
            print('  %-28s ×%d' % (k[:28], v))


def tables_6to8(char, last_logs=5):
    files = sorted(glob.glob(os.path.join(FL_DIR, 'fl_%s_*.pkl' % char)),
                   key=lambda p: (os.path.getmtime(p), p))[-last_logs:]
    if not files:
        print('\n[表6-8] 帧日志无数据(TH123_FRAME_LOG=1后抽样累积)')
        return
    from behavior_health import FL_FIELDS
    from frame_events import FrameEventDetector
    from feat_builder import LOW_ATTACK_IDS_BY_CHAR
    ix = {k: i for i, k in enumerate(FL_FIELDS)}
    flips = speeds = n_frames = 0
    vx_all = []
    dec_gaps = []
    ev_react = []
    # 防守错位矩阵: [防姿(立/蹲/空)] × [来袭(下段/中上段/无段位标记)]
    guard_matrix = {g: {h: 0 for h in ('low', 'high', 'mid')}
                    for g in ('stand', 'crouch', 'air')}
    for p in files:
        try:
            with open(p, 'rb') as fh:
                d = pickle.load(fh)
        except Exception:
            continue
        fr = d['frames']
        if not fr:
            continue
        n_frames += len(fr)
        # 6: 方向翻转率+速度
        prev_dir = None
        prev_x = None
        for (l, r, o, fc) in fr:
            dr = 1 if l[ix['direction']] > 0 else -1
            if prev_dir is not None and dr != prev_dir:
                flips += 1
            prev_dir = dr
            if prev_x is not None:
                vx_all.append(l[ix['position.x']] - prev_x)
            prev_x = l[ix['position.x']]
        # 7: 事件→下一决策帧距 + 决策间隔(离线重放检测器)
        det = FrameEventDetector()
        dec_fs = {f for f, _ in (d.get('decisions') or [])}
        pending_ev = None
        last_dec_i = None
        for i, (l, r, o, fc) in enumerate(fr):
            ev = det.detect(
                {k: l[j] for j, k in enumerate(FL_FIELDS)},
                {k: r[j] for j, k in enumerate(FL_FIELDS)}, False)[0]
            if ev != 0:
                pending_ev = i
            if (i + 1) in dec_fs:      # 决策帧号=局内计数=i+1
                if pending_ev is not None:
                    ev_react.append(i - pending_ev)
                    pending_ev = None
                if last_dec_i is not None:
                    dec_gaps.append(i - last_dec_i)
                last_dec_i = i
        # 8: 防守错位(对手攻击帧×我方防姿)
        low_ids = LOW_ATTACK_IDS_BY_CHAR.get(d.get('opp_char'),
                                             frozenset())
        for (l, r, o, fc) in fr:
            my_a, op_a = int(l[ix['action']]), int(r[ix['action']])
            g = ('stand' if 150 <= my_a <= 153 else
                 'crouch' if 154 <= my_a <= 157 else
                 'air' if my_a == 158 else None)
            if g is None or not (300 <= op_a < 600):
                continue
            h = ('low' if op_a in low_ids else
                 'high' if op_a in _HIGH_IDS_FOR(d.get('opp_char'))
                 else 'mid')
            guard_matrix[g][h] += 1
    print('\n[表6] 位移混乱度 (%d抽样局 %d帧)' % (len(files), n_frames))
    if n_frames:
        print('  方向翻转率 %.2f 次/百帧' % (100.0 * flips / n_frames))
        if len(vx_all) > 10:
            import numpy as np
            v = np.asarray(vx_all, dtype=np.float32)
            ac = float(np.corrcoef(v[:-1], v[1:])[0, 1]) \
                if v.std() > 1e-6 else 1.0
            print('  速度自相关 %.3f (低=位移混乱)' % ac)
    print('[表7] 反应延迟(事件→下一决策帧距 P50/P90 | 决策间隔P50)')
    import numpy as np
    if ev_react:
        g = np.asarray(ev_react, dtype=np.float32)
        print('  事件反应 P50=%.0f帧 P90=%.0f帧 (n=%d)'
              % (float(np.percentile(g, 50)),
                 float(np.percentile(g, 90)), len(g)))
    else:
        print('  事件反应: (本批无事件→决策对)')
    if dec_gaps:
        g2 = np.asarray(dec_gaps, dtype=np.float32)
        print('  决策间隔 P50=%.0f帧 (n=%d)'
              % (float(np.percentile(g2, 50)), len(g2)))
    print('[表8] 防守错位矩阵 (我方防姿×对手来袭段位)')
    for gname, row in guard_matrix.items():
        tot = sum(row.values())
        if tot:
            print('  %-7s n=%-4d 下段%d 中段%d 站防必%d'
                  % (gname, tot, row['low'], row['mid'], row['high']))


def _HIGH_IDS_FOR(opp_char):
    """对手站防必ID集(guard_height.json的high段)。"""
    try:
        p = os.path.join(ROOT, 'data', 'guide_tables',
                         'guard_height.json')
        d = json.load(io.open(p, encoding='utf8'))
        return frozenset(d['high'].get(opp_char, []))
    except Exception:
        return frozenset()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu,marisa,suika')
    ap.add_argument('--last', type=int, default=200)
    ap.add_argument('--logs', type=int, default=5)
    a = ap.parse_args()
    for ch in a.char.split(','):
        prune_sidecars(ch)
        tables_2to5(ch, a.last)
        tables_6to8(ch, a.logs)
        print()


if __name__ == '__main__':
    main()
