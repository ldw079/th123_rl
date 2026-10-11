# -*- coding: utf-8 -*-
"""阶段0(系列对手预测方案§2): 系列位置分桶测量仪表.

两仪表(方案§0目标指标的基线测量点):
  1. aux-系列位置曲线 — 对手下一招预测命中率按"系列内第几场"分桶
     (系列末段 vs 首场的爬升 = 目标+8pp 的基线);
  2. 回合胜率斜率 — 对局胜负按系列位置分层(末场 vs 首场 = 目标+10pp).

系列位置口径: 对手轮换周期5局恰=系列长(方案§3.1据此设计) — episode在
轮换组内的序位(ep%5+1)即"对同一对手连续第几场"(char级系列; 固定快照
系列属阶段1的SeriesManager). actor进程重启会重置ep计数=系列重新从1起,
与"断线忘状态"同构(方案§5.3), 分桶自然吸收.

胜负解码口径: rews的回合结算块 — 胜回合∈[3,13](KO+快胜), 负回合≤-5
(R62败局追扣使负回合深负); 先胜2定局 → 回合胜负数多者胜. 代理保真度
由league重算的对手标签总量交叉验证(R62后回报经济学已回正).

仪表挂点: learner_hub批处理路径(episode消费即删 — P1-C — 唯一可持续
测量点), 批内逐局no_grad前向评分, 曲线随批日志打印.
"""
from __future__ import annotations

import numpy as np

SERIES_LEN = 5        # 轮换周期(=系列长, 方案§3.1)
ROUND_WIN = 3.0       # 胜回合奖励下界(KO 3-13 含快胜)
ROUND_LOSE = -5.0     # 负回合奖励上界(-5..-10, R62追扣更深)
BUCKETS = ('b1', 'b2', 'b3', 'b4-5')


def series_position(ep_idx):
    """episode在轮换组内序位 → 1..SERIES_LEN(即系列内第几场)."""
    return int(ep_idx) % SERIES_LEN + 1


def position_from_meta(meta):
    """系列位置(前向兼容): 阶段1的EP_SCHEMA+1提供match_in_series
    (BO15修订: 15场先到8胜) — 有则优先并钳入现行桶宽(>SERIES_LEN归
    b4-5尾桶); 无则回退轮换组序位. 阶段1落地时桶式扩为15场分段, 此处
    是唯一改动点."""
    try:
        m = int((meta or {}).get('match_in_series', 0))
        if m >= 1:
            return min(m, SERIES_LEN)
    except (TypeError, ValueError):
        pass
    return series_position(int((meta or {}).get('ep', 0)))


def bucket_of(position):
    """:param position: series_position产物 → 分桶标签."""
    if position <= 3:
        return 'b%d' % position
    return 'b4-5'


def decode_match_outcome(rews):
    """rews(np.ndarray) → 'W'/'L'/'?'(回合结算块解码, 先胜2定局)."""
    r = np.asarray(rews, dtype=np.float64)
    w = int((r >= ROUND_WIN).sum())
    l = int((r <= ROUND_LOSE).sum())
    if w > l:
        return 'W'
    if l > w:
        return 'L'
    return '?'


def aux_predict(net, feats, sides, masks, temp, device=None, chunk=512):
    """aux头批前向 → 逐行预测类(np.ndarray int64).

    与learner评分同路径: X=feats/255, Q=net(X,S,temp,M)[2]的argmax.
    no_grad — 仪表不改训练语义.
    """
    import torch
    if device is None:
        from ppo_gpu import DEVICE
        device = device or DEVICE
    preds = []
    with torch.no_grad():
        for i0 in range(0, len(sides), chunk):
            x = torch.from_numpy(
                np.asarray(feats[i0:i0 + chunk])
                .reshape(-1, 3, 60, 80).astype(np.float32) / 255.0
            ).to(device)
            s = torch.from_numpy(
                np.asarray(sides[i0:i0 + chunk],
                           dtype=np.float32)).to(device)
            m = (torch.from_numpy(
                np.asarray(masks[i0:i0 + chunk]).astype(bool)).to(device)
                if masks is not None else None)
            _logits, _v, q = net(x, s, temp, m)
            preds.append(q.argmax(1).cpu().numpy())
    return (np.concatenate(preds) if preds
            else np.zeros(0, dtype=np.int64))


def score_episode_aux(net, arr, temp):
    """单episode aux评分 → (hits, n_valid); 无有效标签→(0,0)(COM局)."""
    opp = np.asarray(arr['opp_next'])
    valid = opp >= 0
    n = int(valid.sum())
    if n == 0:
        return 0, 0
    preds = aux_predict(net, arr['feats'][valid], arr['sides'][valid],
                        arr['masks'][valid], temp)
    return int((preds == opp[valid]).sum()), n


def curve_line(records):
    """[(position, aux_hit|None, aux_n, outcome)] → 曲线文本行.

    每桶: aux命中率(样本=有效预测拍) + 对局胜负(样本=局数).
    """
    agg = {b: {'hits': 0, 'n': 0, 'w': 0, 'l': 0} for b in BUCKETS}
    for pos, hit, n, outcome in records:
        b = agg[bucket_of(pos)]
        if hit is not None and n:
            b['hits'] += hit
            b['n'] += n
        if outcome == 'W':
            b['w'] += 1
        elif outcome == 'L':
            b['l'] += 1
    parts = []
    for b in BUCKETS:
        a = agg[b]
        aux_s = ('%d%%' % round(100.0 * a['hits'] / a['n'])
                 if a['n'] else '-')
        wr_s = ('%d%%' % round(100.0 * a['w'] / (a['w'] + a['l']))
                if (a['w'] + a['l']) else '-')
        parts.append('%s:aux%s(n%d) W%d-%d(%s)'
                     % (b, aux_s, a['n'], a['w'], a['l'], wr_s))
    return ' '.join(parts)
