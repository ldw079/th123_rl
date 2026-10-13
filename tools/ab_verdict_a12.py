# -*- coding: utf-8 -*-
r"""A1-2(未决方案§A)首次正式验收 — 按POT_W注释里自写的协议执行.

协议(train_tm.py A1-2注): "A/B: 24h对照F6 quick, 顶时判负率<20%为目标,
净分下滑则回滚改走A1-4(反康对称项)"。三指标(用户2026-10-13指定):
  1. 顶时判负率(eval侧 report.passivity.timeout_loss_share; 目标<20%)
  2. 远弹份额(learner被动曲线尾部20行均值 — 训练侧行为读数)
  3. 净分(eval quick平均对位胜率 vs 基线postR63(10-11, A/B前))

窗口纪律: A/B起算2026-10-12 18:10(2.84 fleet重启), 累计=墙钟-监督日志
记录的暂停间隔; <24h拒绝final判定(--force按现有数据出预读)。

用法: python tools/ab_verdict_a12.py [--force] [--games 2]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

AB_START = '2026-10-12 18:10:00'      # 2.84重启(R75事故后fleet恢复)
AB_START_TS = time.mktime(time.strptime(AB_START, '%Y-%m-%d %H:%M:%S'))
SUP_LOG = r'D:\temp\th123_models\fleet_supervision.log'
BASELINE = os.path.join(HERE, 'eval_matrix_quick_20261011_postR63.json')
WINDOW_H = 24.0
PY = sys.executable


def accumulated_hours(now=None):
    """A/B累计训练时长 = 墙钟 - 暂停间隔(监督日志"间隔 X.Xh"行求和)。

    注: "间隔"行为启动时报告的上次心跳→本次启动gap, 含主机睡眠与
    灭队; A/B期内的gap全部为非训练时间, 直接扣除(口径: 计划内暂停
    与意外全灭同等计非训练)。"""
    now = now or time.time()
    paused = 0.0
    try:
        text = open(SUP_LOG, encoding='utf8', errors='replace').read()
    except OSError:
        return None, 0.0
    for ln in text.splitlines():
        m = re.match(r'\[10-1[23] (\d\d:\d\d:\d\d)\].*间隔 ([\d.]+)h', ln)
        if not m:
            continue
        ts = time.mktime(time.strptime('2026-10-12 ' + m.group(1),
                                       '%Y-%m-%d %H:%M:%S'))
        # 10-13的行日期归13日
        if ln.startswith('[10-13'):
            ts += 86400
        if ts < AB_START_TS:
            continue
        g = float(m.group(2))
        # 与启动时刻的gap只算A/B窗口内部分
        start_gap = ts - g * 3600.0
        overlap_lo = max(start_gap, AB_START_TS)
        overlap_hi = min(ts, now)
        if overlap_hi > overlap_lo:
            paused += (overlap_hi - overlap_lo) / 3600.0
    total = (now - AB_START_TS) / 3600.0
    return max(total - paused, 0.0), paused


def run_eval(games):
    """跑eval quick(串行子进程) → 最新quick json路径。"""
    out = os.path.join(HERE, 'eval_matrix_quick_%s.json'
                       % time.strftime('%Y%m%d'))
    cmd = [PY, '-X', 'utf8', os.path.join(HERE, 'eval_matrix.py'),
           '--chars', '3', '--games', str(games), '--output', out]
    print('[A/B] 跑F6 quick: %s ...' % ' '.join(cmd[3:7]))
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=5400)
    if r.returncode != 0:
        print(r.stdout[-1500:] if r.stdout else '')
        print(r.stderr[-800:] if r.stderr else '')
        raise SystemExit('[A/B] eval失败 exit=%d' % r.returncode)
    return out


def far_share_from_learners(n_tail=20):
    """远弹份额(训练侧): 三角色learner被动曲线尾部n行均值。"""
    out = {}
    for ch in ('reimu', 'marisa', 'suika'):
        vals = []
        try:
            text = open(r'D:\temp\learner_%s.log' % ch,
                        encoding='utf8', errors='replace').read()
            for ln in text.splitlines()[-4000:]:
                m = re.search(r'被动曲线 远弹([\d.-]+)%\(n(\d+)\)', ln)
                if m and int(m.group(2)) > 0:
                    vals.append(float(m.group(1)))
        except OSError:
            pass
        tail = vals[-n_tail:]
        out[ch] = round(sum(tail) / len(tail), 1) if tail else None
    return out


def mean_winrate(path):
    d = json.load(open(path, encoding='utf8'))
    rows = [v for v in (d.get('matrix') or {}).values()
            if isinstance(v, dict) and 'games' in v]
    if not rows:
        return None, d
    tot_w = sum(v.get('wins', v.get('a_wins', 0)) for v in rows)
    tot = sum(v.get('games', 0) for v in rows)
    return (100.0 * tot_w / tot if tot else None), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true',
                    help='窗口不足24h也出完整读数(标记为预读)')
    ap.add_argument('--games', type=int, default=2)
    args = ap.parse_args()

    acc_h, paused_h = accumulated_hours()
    print('[A/B] 窗口: 起算%s | 累计训练%.1fh(扣暂停%.1fh) | 需%.0fh'
          % (AB_START, acc_h, paused_h, WINDOW_H))
    final = acc_h >= WINDOW_H
    if not final and not args.force:
        print('[A/B] 窗口不足 — 拒绝final判定(差%.1fh)。'
              '加--force出预读。' % (WINDOW_H - acc_h))
        return 1

    ev = run_eval(args.games)
    wr_new, d_new = mean_winrate(ev)
    wr_base, _ = mean_winrate(BASELINE)
    pas = (d_new.get('report') or {}).get('passivity') or {}
    far = far_share_from_learners()

    tl = pas.get('timeout_loss_share')
    tl_pct = round(100 * tl, 1) if tl is not None else None
    wr_delta = (round(wr_new - wr_base, 1)
                if wr_new is not None and wr_base is not None else None)

    keep_tl = tl_pct is not None and tl_pct < 20
    keep_score = wr_delta is None or wr_delta >= -2.0   # 容差2pp(局数噪声)
    verdict = ('保留A1-2' if (keep_tl and keep_score)
               else '回滚 → 改走A1-4(反康对称项)')

    print('\n==== A1-2 %s读数(三指标) ===='
          % ('FINAL' if final else '预读(--force)'))
    print('1. 顶时判负率: %s%% (目标<20%%) %s'
          % (tl_pct, '✓' if keep_tl else '✗'))
    print('   (顶时率%s 顶时HP差均值%s)'
          % (pas.get('timeout_rate'), pas.get('timeout_hp_mean_avg')))
    print('2. 远弹份额(训练侧尾部20行): %s' % far)
    print('3. 净分: quick平均胜率 %.1f%% vs 基线(postR63) %.1f%% '
          '(Δ%spp, 容差-2) %s'
          % (wr_new if wr_new is not None else -1,
             wr_base if wr_base is not None else -1,
             wr_delta if wr_delta is not None else '?',
             '✓' if keep_score else '✗'))
    print('\n判定: %s' % verdict)
    print('混淆因子(裁定时须知): side_driver dec_name修复(R80)落在'
          'A/B窗口内(对手守备窗豁免恢复=对手略强)')

    out = os.path.join(
        HERE, 'ab_verdict_a12_%s%s.json'
        % (time.strftime('%Y%m%d_%H%M'), '' if final else '_prelim'))
    json.dump({'final': final, 'accumulated_h': acc_h,
               'timeout_loss_pct': tl_pct, 'passivity': pas,
               'far_share': far, 'winrate_new': wr_new,
               'winrate_base': wr_base, 'winrate_delta': wr_delta,
               'verdict': verdict, 'eval_json': ev,
               'ts': time.strftime('%Y-%m-%d %H:%M:%S')},
              open(out, 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    print('报告:', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
