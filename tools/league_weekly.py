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


def exploit_decay(blocks):
    """W5(研究借鉴方案§5): exploit_快照胜率随暴露局数的衰减读数.

    跨块行是**累积值**(scratch stats) — 局数回退=actor重启, 按分段
    取最长段分析。主策略视角W-L换算剥削者胜率=1-主胜率。
    判读(语言对齐笔记§8.9): 剥削者胜率维持>0.5 → "持续克制(主策略
    弱点未修复)"; 中段跌破初值一半 → 估半衰期局数; ≤3块归零 →
    "一次性奇袭(已适应)"。
    """
    series = {}
    for b in blocks:
        for lab, w, l in b['rows']:
            if '@exploit_' not in lab:
                continue
            n = w + l
            if n >= 1:
                series.setdefault(lab, []).append(
                    (n, w / n, b.get('ts', '')))
    out = {}
    for lab, pts in series.items():
        segs, cur = [], []
        for p in pts:
            if cur and p[0] < cur[-1][0]:
                segs.append(cur)
                cur = []
            cur.append(p)
        segs.append(cur)
        seg = max(segs, key=len)
        n0, wr0, ts0 = seg[0]
        n1, wr1, ts1 = seg[-1]
        e0, e1 = 1.0 - wr0, 1.0 - wr1
        if e1 > 0.5:
            verdict = '持续克制(主策略弱点未修复)'
        elif e1 < 0.5 * max(e0, 1e-9) and n1 - n0 >= 4:
            verdict = '半衰期约%d局(暴露后适应)' % (n1 - n0)
        elif n1 <= 3 or (n1 - n0) <= 3:
            verdict = '一次性奇袭(已适应)'
        else:
            verdict = '部分适应'
        out[lab] = {'games': n1, 'main_wr_first': round(wr0, 3),
                    'main_wr_last': round(wr1, 3),
                    'exploit_wr_first': round(e0, 3),
                    'exploit_wr_last': round(e1, 3),
                    'ts_span': [ts0, ts1], 'verdict': verdict}
    return out


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
        'exploit_decay': exploit_decay(blocks),
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
    # W5: exploit半衰期小节(负结果入档语言)
    if rep.get('exploit_decay'):
        print('exploit衰减(W5, 主策略视角):')
        for lab, d in rep['exploit_decay'].items():
            print('  %s 暴露%d局 主胜率%.0f%%→%.0f%% | %s'
                  % (lab.split('@')[0] + '@' + lab.split('@')[1][:20],
                     d['games'], d['main_wr_first'] * 100,
                     d['main_wr_last'] * 100, d['verdict']))
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
