# -*- coding: utf-8 -*-
"""R48: League调度器 — 胜率加权对手选择(fictitious play式)。

设计(可行性报告天花板5):
- R43动态池提供"最新快照自动入局" — 本模块在其上叠加**胜率加权**:
  对当前模型胜率高的对手(强敌)获得更多采样权重
- 剥削者概念: 当某对手胜率 <20% 持续50局, 标记为"已解决",
  权重降低(避免永远打已碾压的旧对手); 当某对手胜率 >80%,
  权重提高(需要更多对抗强敌的学习信号)

实现: 每角色维护 opponent_stats = {label: [W, L]},
     权重 = base_weight × f(winrate) × recency_bonus
     f(wr) = wr^2 (胜率越高权重越大 — fictitious play标准形式)
     recency_bonus = 1.0 (可扩展: 新快照额外加权)

接入点: train_tm._resolve_pool 在取latest(K)后用league权重选一个
(替代纯轮转指针)。
"""
from __future__ import annotations

import math


def league_weight(wins: int, losses: int, min_games: int = 5) -> float:
    """对手的league采样权重。

    fictitious play: 对强敌(高胜率=模型打不过)加权更多。
    - 胜率 wr = W/(W+L), 权重 ∝ wr^1.5 (非线性: 强敌远比弱敌重要)
    - 不足min_games局: 权重=0.5 (中性, 需要数据)
    - 完全碾压(模型胜率>80%即对手wr<20%): 权重×0.3
      (已解决的对手不值得大量采样)
    """
    n = wins + losses
    if n < min_games:
        return 0.5
    # wr = 模型对这对手的胜率
    wr = wins / n
    # 模型胜率低(=对手强) → 权重高
    opp_strength = 1.0 - wr
    w = opp_strength ** 1.5
    # 模型碾压(wr>0.8) → 额外降权
    if wr > 0.8:
        w *= 0.3
    return max(0.05, w)


def pick_weighted(candidates: list, stats: dict,
                  rng) -> tuple:
    """从候选对手中按league权重选一个。

    candidates: [(char, model_path), ...]
    stats: {label: [W, L]} — 当前模型的对手统计
    rng: random.Random实例
    返回: (char, model_path) 选中的对手
    """
    if not candidates:
        return None, None
    if len(candidates) == 1:
        return candidates[0]

    weights = []
    for ch, path in candidates:
        # 从path提取label(train_tm._opp_label格式: char@timestamp)
        ts = path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]
        ts = ts.replace('.npz', '')
        label = '%s@%s' % (ch, ts)
        w, l = stats.get(label, [0, 0])
        weights.append(league_weight(w, l))

    # 归一化+加权随机
    total = sum(weights)
    if total <= 0:
        return candidates[rng.randrange(len(candidates))]
    probs = [w / total for w in weights]
    idx = rng.choices(range(len(candidates)), weights=probs)[0]
    return candidates[idx]


def league_report(stats: dict, top: int = 5) -> str:
    """League状态报告文本。"""
    lines = []
    ranked = sorted(stats.items(),
                    key=lambda kv: -(kv[1][0] + kv[1][1]))
    for label, (w, l) in ranked[:top]:
        n = w + l
        wr = w / n if n > 0 else 0
        wt = league_weight(w, l)
        lines.append('  %-30s %3dW-%3dL (%.0f%%) 权重%.2f'
                     % (label, w, l, wr * 100, wt))
    return '\n'.join(lines)
