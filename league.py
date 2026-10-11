# -*- coding: utf-8 -*-
"""R48: League调度器 — 胜率加权对手选择(fictitious play式)。

设计(可行性报告天花板5):
- R43动态池提供"最新快照自动入局" — 本模块在其上叠加**胜率加权**:
  stats记的是**模型**对每个对手的胜率; 模型胜率低(=对手强/难打)
  的对手获得更多采样权重
- 剥削者概念: 模型对某对手胜率>80%(=已碾压)持续, 权重×0.3
  (已解决的对手不值得大量采样); 模型胜率<20%(=被碾压的强敌)
  权重最高(fictitious play: 强敌远比弱敌重要)
  (R61f: 原docstring把方向写反了 — stats是模型胜率非对手胜率,
  "胜率>80%权重提高"与实现的降权0.3×恰好相反, 从零审计"docstring")

实现: 每角色维护 opponent_stats = {label: [W, L]},
     权重 = (1-wr)^1.5 × 碾压降权(×0.3 if wr>0.8), 下限0.05

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


def league20_opps(char, focus=('reimu', 'marisa', 'suika'), weight=3):
    """D3'(R65): 20角色league的actor对手周期构建(单源, supervisor+actor共用).

    组成: 主角色块(focus全角色, 含镜像)×weight + league角色(focus外全量)
    + COM。份额示例(focus=3, weight=3): 周期长27 — 镜像/每个主角色各11%,
    17个league角色各3.7%, COM 3.7%。

    设计要点:
    - 主角色位是"活"对手(learner持续发池快照, league加权在快照间起作用);
      league位是"静"对手(seed_league_pool一次性种子, 标签永不变=stats
      可跨天累积, 中性期(min_games=5)过后league权重对静态位同样生效)。
    - 镜像位保留在主角色块内(自对弈语义不变, 与exploiter的锁死镜像互不干扰)。
    - COM位保留但降份额(原25%→3.7%): COM已0-16L无梯度, C对抗池的
      VS_PLAYER卡组对手才是主训练信号。
    - 池空安全: league角色无快照时_resolve_pool返回None → 轮换跳过
      (train_tm既有语义), 不炸局。
    """
    # 交错而非连排: [r,m,s]*3 而非 [r,r,r,m,m,m,s,s,s] — 计数相同,
    # 但同对手最长连打1轮(5局)而非3轮(15局), 轮换多样性更好。
    block = list(focus) * int(weight)
    league = []
    from train_tm import CHAR_LIBS
    for ch in CHAR_LIBS:
        if ch not in focus:
            league.append(ch)
    return block + league + ['COM']
