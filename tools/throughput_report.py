# -*- coding: utf-8 -*-
"""F(未决问题方案§F): fleet吞吐标定 — 本机actor数-吞吐曲线的实测账.

数据源(纯离线): 三类既有日志 —
  1. actor日志 [actorN] HH:MM:SS epX ... 行 → 按连续段(ep回落=进程重启)
     计算局/小时/actor;
  2. learner日志 批N局/M决策 Ts.v → 批耗时分布(安静机基准17.7s对照);
  3. fleet_supervision.log 行时间戳 → 间隙>10min=停机 → 占空比
     (C1-1心跳的日志版; 48h运营窗口的"窗口"定义即此).

验收口径(D2'收官): 给出当前配置(2actor/tps300)的实测吞吐与
learner批耗时带, 配置变化后复跑对比即得拐点。
用法: python tools/throughput_report.py [--hours 48] [--output json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
SUP_LOG = os.path.join(STORE, 'fleet_supervision.log')
ACTOR_LOG = r'D:\temp\actor_%s_%d.log'
LEARNER_LOG = r'D:\temp\learner_%s.log'

_RE_ACTOR_EP = re.compile(
    r'\[actor(\d+)\] (\d{2}:\d{2}:\d{2}) ep(\d+) ')
_RE_BATCH = re.compile(r'批\d+局/\d+决策 ([\d.]+)s v\d+')
_RE_SUP_TS = re.compile(r'\[(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2})\]')


def _parse_hms(s):
    h, m, sec = s.split(':')
    return int(h) * 3600 + int(m) * 60 + int(sec)


def actor_rates(paths):
    """逐actor: 按ep连续段计算局/小时。跨天段(HM回绕)按+24h处理。"""
    out = {}
    for path in paths:
        segs = []
        cur = []
        prev_ep, day = None, 0
        try:
            text = open(path, encoding='utf8', errors='replace').read()
        except OSError:
            continue
        for m in _RE_ACTOR_EP.finditer(text):
            t, ep = _parse_hms(m.group(2)), int(m.group(3))
            if prev_ep is not None and ep < prev_ep:
                segs.append(cur)
                cur = []
                day = 0     # 新进程, 时间重新起算
            if cur and t < cur[-1][0]:
                day += 86400
            cur.append((t + day, ep))
            prev_ep = ep
        if cur:
            segs.append(cur)
        rates = []
        for seg in segs:
            if len(seg) >= 2 and seg[-1][0] > seg[0][0]:
                dt_h = (seg[-1][0] - seg[0][0]) / 3600.0
                deps = seg[-1][1] - seg[0][1]
                if dt_h > 0.02 and deps > 0:
                    rates.append((round(deps / dt_h, 2), deps,
                                  round(dt_h, 2)))
        if rates:
            out[os.path.basename(path)] = rates
    return out


def batch_durations(chars, last_n=100):
    """逐角色learner批耗时分布(秒): (n, median, p90, max)。"""
    import statistics
    out = {}
    for ch in chars:
        try:
            text = open(LEARNER_LOG % ch, encoding='utf8',
                        errors='replace').read()
        except OSError:
            continue
        ds = [float(m.group(1)) for m in _RE_BATCH.finditer(text)][-last_n:]
        if ds:
            ds.sort()
            out[ch] = {
                'n': len(ds),
                'median': round(ds[len(ds) // 2], 1),
                'p90': round(ds[int(len(ds) * 0.9) - 1 if len(ds) >= 10
                                else -1], 1),
                'max': round(ds[-1], 1),
            }
    return out


GAP_DEAD_S = 4200    # >league重算间隔(3600s)+余量才判停机(分辨率
                     # ~70min: 活着的supervisor最久1h打一行league重算,
                     # 600s阈值会误判"活着但安静")


def duty_cycle(hours=48):
    """监督日志行时间戳 → 间隙>600s计停机; 返回(在线比, 在线h, 停机h)。"""
    try:
        text = open(SUP_LOG, encoding='utf8', errors='replace').read()
    except OSError:
        return None
    now = _dt.datetime.now()
    stamps = []
    for m in _RE_SUP_TS.finditer(text):
        try:
            t = _dt.datetime(now.year, int(m.group(1)), int(m.group(2)),
                             *_map_hms(m.group(3)))
        except ValueError:
            continue
        if t > now:      # 跨年回绕(12月日志在1月读)
            t = t.replace(year=now.year - 1)
        stamps.append(t)
    if len(stamps) < 2:
        return None
    t0 = max(stamps[0], now - _dt.timedelta(hours=hours))
    window = (now - t0).total_seconds()
    online = 0.0
    downtime = 0.0
    prev = None
    for t in stamps:
        if t < t0:
            prev = t
            continue
        if prev is not None:
            gap = (t - prev).total_seconds()
            if gap > GAP_DEAD_S:
                downtime += gap
            else:
                online += gap
        prev = t
    if prev is not None and prev < now:
        tail = (now - prev).total_seconds()
        hb_fresh = False
        try:
            hb_fresh = (now - _dt.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(
                    STORE, 'fleet_heartbeat')))).total_seconds() < 90
        except OSError:
            pass
        if hb_fresh or tail <= GAP_DEAD_S:
            online += tail
        else:
            downtime += tail
    tot = online + downtime
    return {'window_h': round(tot / 3600, 2),
            'online_h': round(online / 3600, 2),
            'downtime_h': round(downtime / 3600, 2),
            'duty': round(online / tot, 3) if tot > 0 else None}


def _map_hms(s):
    h, m, sec = s.split(':')
    return int(h), int(m), int(sec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=int, default=48)
    ap.add_argument('--output', default=None)
    args = ap.parse_args()

    import glob
    rates = actor_rates(glob.glob(r'D:\temp\actor_*.log'))
    print('=== 每actor局/小时(按进程连续段) ===')
    fleet_eps_h = 0.0
    import time as _t
    for name, rs in sorted(rates.items()):
        last = rs[-1]
        path = os.path.join(r'D:\temp', name)
        fresh = False
        try:
            fresh = _t.time() - os.path.getmtime(path) < 1800
        except OSError:
            pass
        print('  %-24s 段数%d 最新段 %.2f局/h(%d局/%.1fh)%s'
              % (name, len(rs), last[0], last[1], last[2],
                 '' if fresh else ' [陈旧档不计入合计]'))
        if fresh:
            fleet_eps_h += last[0]
    print('  fleet合计(仅mtime<30min的活跃档): %.2f局/h' % fleet_eps_h)
    print('=== learner批耗时分布(秒, 近100批; 安静机基准17.7) ===')
    for ch, d in batch_durations(('reimu', 'marisa', 'suika')).items():
        print('  %-8s n=%d median=%.1f p90=%.1f max=%.1f'
              % (ch, d['n'], d['median'], d['p90'], d['max']))
    dc = duty_cycle(args.hours)
    print('=== 占空比(%dh窗) ===' % args.hours)
    if dc:
        print('  窗口%.1fh 在线%.1fh 停机%.1fh 占空比%.0f%%'
              % (dc['window_h'], dc['online_h'], dc['downtime_h'],
                 (dc['duty'] or 0) * 100))
    else:
        print('  监督日志不足')
    rep = {'actor_rates': rates, 'batch': batch_durations(
        ('reimu', 'marisa', 'suika')), 'duty': dc}
    if args.output:
        tmp = args.output + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.output)
        print('报告:', args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
