# -*- coding: utf-8 -*-
"""D1-1(未决问题方案§D): league周报 — 固化指数+末位保护线.

数据源(纯离线): fleet_supervision.log 的 league重算块 —
  "  <opp_char>@<snap>  xW- yL (z%) 权重w" 行(注意: 这是**主策略视角**
  的对手战绩, 即对手label胜率=主策略败率...反之亦然 — 读数方向:
  该行W/L是**主策略**对该对手的胜负).

指标:
  1. 固化指数 = 滚动窗口内"单一对手label占总局数份额"的最大值
     (份额>50%=主策略长期刷同一对手=固化信号);
  2. 末位保护线 = 任一对手族群(char级聚合)主策略胜率 <30% 触发报告行;
  3. char级聚合战绩(对每个对手角色的合计W-L) — D1-3均衡施治的观察钩.

用法: python tools/league_weekly.py [--blocks 10] [--output json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

SUP_LOG = os.path.join(
    os.environ.get('TH123_STORE', r'D:\temp\th123_models'),
    'fleet_supervision.log')

_RE_ROW = re.compile(
    r'^\s+(\S+@\S+|COM)\s+(\d+)W-\s*(\d+)L \((\d+)%\) 权重([\d.]+)')
_RE_TS = re.compile(r'^\[(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2})\] league重算')


def parse_league_blocks(path, max_blocks=None):
    """→ [ {'ts': str, 'rows': [(label, w, l)], } ... ] 按时间序."""
    try:
        lines = open(path, encoding='utf8', errors='replace').read().splitlines()
    except OSError:
        return []
    blocks, cur = [], None
    for ln in lines:
        m = _RE_TS.match(ln)
        if m:
            if cur:
                blocks.append(cur)
            cur = {'ts': '%s %s %s' % m.groups(), 'rows': []}
            # marker同行常带首个对手行(真实格式: "league重算:   COM ...")
            m2 = _RE_ROW.match(ln[m.end():].replace('league重算:', ''))
            if not m2:
                rest = ln.split('league重算:', 1)[-1]
                m2 = _RE_ROW.match('  ' + rest if rest else '')
            if m2:
                cur['rows'].append((m2.group(1), int(m2.group(2)),
                                    int(m2.group(3))))
            continue
        if cur is not None:
            m2 = _RE_ROW.match(ln)
            if m2:
                cur['rows'].append((m2.group(1), int(m2.group(2)),
                                    int(m2.group(3))))
                continue
            if ln.strip() and not ln.startswith('  '):
                blocks.append(cur)
                cur = None
    if cur:
        blocks.append(cur)
    return blocks[-max_blocks:] if max_blocks else blocks


def char_of(label):
    return label.split('@')[0] if '@' in label else label


def analyze(blocks, floor=0.30):
    """固化指数+末位保护线+char级聚合."""
    all_rows = [r for b in blocks for r in b['rows']]
    if not all_rows:
        return None
    # 审计#3 P2披露: all_rows为**跨league重算块累积求和** — 绝对局数
    # 随块数膨胀, 固化指数/胜率等比例量不受影响; blocks_n随报告输出
    total_games = sum(w + l for _lab, w, l in all_rows) or 1
    # 1. 固化指数: 单一label局数份额最大值
    label_games = {}
    for lab, w, l in all_rows:
        label_games[lab] = label_games.get(lab, 0) + w + l
    consolidation = max(label_games.values()) / total_games
    # 2. char级聚合(主策略视角胜率)
    char_agg = {}
    for lab, w, l in all_rows:
        c = char_of(lab)
        a = char_agg.setdefault(c, [0, 0])
        a[0] += w
        a[1] += l
    floor_breach = []
    for c, (w, l) in sorted(char_agg.items()):
        n = w + l
        if n >= 4 and w / n < floor:
            floor_breach.append('%s %.0f%%(%dW-%dL)' % (c, 100 * w / n, w, l))
    return {
        'blocks': len(blocks),
        'total_games': total_games,
        'consolidation_index': round(consolidation, 3),
        'blocks_n': len(blocks),
        'top_label': max(label_games, key=label_games.get),
        'char_agg': {c: {'w': w, 'l': l, 'wr': round(w / (w + l), 3)
                         if w + l else None}
                     for c, (w, l) in sorted(char_agg.items())},
        'floor_breach': floor_breach,
        'floor': floor,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blocks', type=int, default=10)
    ap.add_argument('--floor', type=float, default=0.30)
    ap.add_argument('--output', default=None)
    args = ap.parse_args()
    blocks = parse_league_blocks(SUP_LOG, args.blocks)
    rep = analyze(blocks, args.floor)
    if not rep:
        print('无league重算块')
        return 1
    print('=== league周报(近%d块, %d局) ===' % (rep['blocks'],
                                                 rep['total_games']))
    print('固化指数: %.3f (最大单一对手=%s 占%.0f%%)%s'
          % (rep['consolidation_index'], rep['top_label'],
             rep['consolidation_index'] * 100,
             ' ⚠>50%固化信号' if rep['consolidation_index'] > 0.5 else ''))
    print('char级聚合(主策略视角):')
    for c, d in rep['char_agg'].items():
        wr = d['wr']
        print('  vs %-8s %dW-%dL (%s)' % (c, d['w'], d['l'],
              ('%.0f%%' % (wr * 100)) if wr is not None else '-'))
    if rep['floor_breach']:
        print('⚠ 末位保护线(<%.0f%%): %s' % (rep['floor'] * 100,
              ' / '.join(rep['floor_breach'])))
    else:
        print('末位保护线: 无触发(或样本<4局)')
    if args.output:
        tmp = args.output + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.output)
        print('报告:', args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
