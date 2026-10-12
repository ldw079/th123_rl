# -*- coding: utf-8 -*-
"""H(未决问题方案§H): 纵向学习曲线 — 训练日志→时间序列+平台期检测.

数据源(纯离线, 零CPU争用): D:/temp/learner_{char}.log 的两类行 —
  1. 批行: [learner] {char} 批N局/M决策 Ts vVER |KL|K 熵E 值损V 陈旧S
     [aux命中A%]  → (ver, kl, entropy, value_loss, aux)
  2. 曲线行(10-12后): 系列曲线 b1:auxX%(nN) ... / 被动曲线 远弹X%(nN)
     逼近Y% 开局攻Z%  → (b1_aux, b4_5_aux, far_bullet, closing,
     opening_attack)

平台期检测 = 末TAIL(默认500)个更新点上 aux/熵 的线性回归斜率
(斜率近零=平台; aux以%/点计, 熵以1e-3/点计的阈值判定)。

用法: python tools/learning_curve.py [--chars reimu,marisa,suika]
       [--tail 500] [--output json路径]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

LOG_DIR = os.environ.get('TH123_LEARNER_LOG_DIR', r'D:' + chr(92) + 'temp')  # supervisor硬编码该目录
LOG_GLOB = os.path.join(LOG_DIR, 'learner_%s.log')

# 批行: ... v142 |KL|0.0883 熵1.98 值损22.59 陈旧2 aux命中54%
_RE_BATCH = re.compile(
    r'v(\d+) \|KL\|([\d.]+) 熵([\d.]+) 值损([\d.]+) 陈旧\d+'
    r'(?: aux命中([\d.]+)%)?')
# 系列曲线行: ... b1:aux64%(n379) ... b4-5:aux68%(n1940) ...
_RE_SERIES = re.compile(r'b1:aux([\d.-]+)%\(n(\d+)\).*?b4-5:aux([\d.-]+)%')
# 被动曲线行: 被动曲线 远弹50%(n4) 逼近75% 开局攻38%
_RE_PASSIVE = re.compile(
    r'被动曲线 远弹([\d.-]+)%\(n(\d+)\) 逼近([\d.-]+)% 开局攻([\d.-]+)%')

AUX_PLATEAU_SLOPE = 0.002    # %/更新点 — 末段每更新提升<0.2pp=平台
ENT_PLATEAU_SLOPE = 1e-4     # 熵单位/更新点


def parse_learner_log(path):
    """→ {'batch': [(ver,kl,ent,vloss,aux|None)...],
         'series': [(b1,b1_n,b45)...], 'passive': [(far,n,close,open)...]}"""
    out = {'batch': [], 'series': [], 'passive': []}
    try:
        text = open(path, encoding='utf8', errors='replace').read()
    except OSError:
        return out
    for line in text.splitlines():
        m = _RE_BATCH.search(line)
        if m:
            out['batch'].append((int(m.group(1)), float(m.group(2)),
                                 float(m.group(3)), float(m.group(4)),
                                 float(m.group(5)) if m.group(5) else None))
            continue
        m = _RE_SERIES.search(line)
        if m:
            out['series'].append((float(m.group(1)), int(m.group(2)),
                                  float(m.group(3))))
            continue
        m = _RE_PASSIVE.search(line)
        if m:
            out['passive'].append((float(m.group(1)), int(m.group(2)),
                                   float(m.group(3)), float(m.group(4))))
    return out


def tail_slope(points, tail=500):
    """(x,y)序列末tail点线性回归斜率; None=样本不足/含None。"""
    pts = [(x, y) for x, y in points if y is not None]
    if len(pts) < 10:
        return None
    pts = pts[-tail:]
    n = len(pts)
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        return None
    return (n * sxy - sx * sy) / denom


def analyze_char(path, tail=500):
    d = parse_learner_log(path)
    batch = d['batch']
    aux_pts = [(v, a) for v, _k, _e, _l, a in batch if a is not None]
    ent_pts = [(v, e) for v, _k, e, _l, _a in batch]
    aux_slope = tail_slope(aux_pts, tail)
    ent_slope = tail_slope(ent_pts, tail)
    verdict = None
    if aux_slope is not None:
        verdict = ('平台(aux末段斜率%.2g %%/点 < %.2g)'
                   % (aux_slope, AUX_PLATEAU_SLOPE)
                   if abs(aux_slope) < AUX_PLATEAU_SLOPE else
                   '上升(aux %.2g %%/点)' % aux_slope)
    series = d['series']
    passive = d['passive']
    return {
        'log': path,
        'updates': (batch[-1][0] - batch[0][0] + 1) if batch else 0,
        'n_batches': len(batch),
        'aux_last': (aux_pts[-1][1] if aux_pts else None),
        'entropy_last': (ent_pts[-1][1] if ent_pts else None),
        'aux_tail_slope': aux_slope,
        'entropy_tail_slope': ent_slope,
        'plateau_verdict': verdict,
        'series_lines': len(series),
        'series_b1_last': (series[-1][0] if series else None),
        'series_b45_last': (series[-1][2] if series else None),
        'passive_lines': len(passive),
        'far_bullet_last': (passive[-1][0] if passive else None),
        'closing_last': (passive[-1][2] if passive else None),
        'opening_attack_last': (passive[-1][3] if passive else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--tail', type=int, default=500)
    ap.add_argument('--output', default=None)
    args = ap.parse_args()
    report = {}
    for ch in args.chars.split(','):
        ch = ch.strip()
        if not ch:
            continue
        r = analyze_char(LOG_GLOB % ch, args.tail)
        report[ch] = r
        print('--- %s ---' % ch)
        print('  批数%d 跨v%d个更新 | aux末值%s 熵末值%s'
              % (r['n_batches'], r['updates'],
                 r['aux_last'], r['entropy_last']))
        print('  平台期: %s (熵斜率%s)'
              % (r['plateau_verdict'],
                 ('%.2g' % r['entropy_tail_slope'])
                 if r['entropy_tail_slope'] is not None else 'n/a'))
        print('  系列曲线%d条(b1末%s b4-5末%s) | 被动曲线%d条'
              '(远弹末%s%% 逼近末%s%% 开局攻末%s%%)'
              % (r['series_lines'], r['series_b1_last'],
                 r['series_b45_last'], r['passive_lines'],
                 r['far_bullet_last'], r['closing_last'],
                 r['opening_attack_last']))
    if args.output:
        tmp = args.output + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.output)
        print('报告:', args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
