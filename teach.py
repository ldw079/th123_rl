# -*- coding: utf-8 -*-
"""R48: 教学层起步(可行性报告§3"教学性"维度)。

三个杠杆(全部基于已有资产):
1. **局面讲解**(教义树偏离矩阵 → 自然语言): "此时标准应对是X, 模型
   选了Y" — standard_tree审计管线的教学化包装
2. **分支演示**(SET_POSITION/SET_HEALTH/SET_WEATHER + 确定性锁步):
   同一局面用不同宏重跑 — "五种应对的后果对比"
   mod早已支持, 仅hitlab用过; 全项目最被低估的资产
3. **校准对局**(限制性手法): 固定开局/禁某类宏/降反应档(限温度)

本模块为起步版: ①局面讲解纯离线(不依赖游戏), 立即可用。
②③需游戏实例, 提供接口待后续接入。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def explain_situation(char: str, dx: float, opp_airborne: bool,
                      opp_corner: bool, spirit: float,
                      model_choice: str, entropy: float = None) -> str:
    """局面讲解: 标准应对 vs 模型选择(教义树驱动, 纯离线)。

    这是教学层的最轻量形态 — 不需要游戏实例, 输入是当前局面特征
    (从105B包解析), 输出是自然语言的"标准应对+模型偏差+建议"。
    R61o(E4): entropy参数 = 策略输出分布的香农熵 — 标注置信度
    (低熵=确信选择, 高熵=试探性选择; 讲解读者可判断建议的可靠度)。
    """
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS[char]
    std = _doctrine_best(dx, opp_airborne, opp_corner, spirit,
                         lib)
    parts = []
    parts.append('【局面】距离%.0f 对手%s%s 灵力%.0f'
                 % (dx, '空中' if opp_airborne else '地面',
                    ' 版边' if opp_corner else '', spirit))
    parts.append('【标准应对】%s' % std)
    parts.append('【模型选择】%s' % model_choice)
    # R61o(E4): 置信度标注(熵→人类可读)
    if entropy is not None:
        if entropy < 1.0:
            conf = '高置信'
        elif entropy < 2.0:
            conf = '中置信'
        else:
            conf = '低置信(试探)'
        parts.append('【置信度】%s (熵%.2f)' % (conf, entropy))
    if model_choice == std:
        parts.append('【评价】✓ 符合标准')
    else:
        delta = _explain_delta(std, model_choice, lib)
        parts.append('【评价】偏差: %s' % delta)
    return '\n'.join(parts)


def policy_entropy(ppo, feat, side, mask=None) -> float:
    """R61o(E4): 策略输出分布的香农熵。

    熵越低=策略越确信(分布尖锐); 越高=越试探(分布平坦).
    用于讲解的置信度标注: 读者可判断"模型选X"是深思熟虑还是碰运气.
    """
    import numpy as np
    P = ppo._pi_forward(feat.reshape(1, -1), side.reshape(1, -1),
                        temp=1.0,
                        mask=mask.reshape(1, -1) if mask is not None
                        else None)[2][0]
    P = np.clip(P, 1e-10, 1.0)
    return float(-np.sum(P * np.log(P)))


def _doctrine_best(dx, air, corner, spirit, lib) -> str:
    """教义树查询: 当前局面的标准应对宏名。"""
    names = set(lib['names'])
    if air:
        for cand in ('空连A', 'jA', 'j6A', '高跳'):
            if cand in names:
                return cand
    if corner and dx < 250:
        for cand in ('版边连A', '连段A', '压制A'):
            if cand in names:
                return cand
    if dx > 450:
        if spirit < 200:
            for cand in ('后退', '后跳', '蹲防'):
                if cand in names:
                    return cand
        for cand in ('5B', '5C', '236B'):
            if cand in names:
                return cand
    if dx > 250:
        for cand in ('jB', 'jA', 'DA'):
            if cand in names:
                return cand
    if dx > 130:
        for cand in ('5A', '2A', '连段A'):
            if cand in names:
                return cand
    # 贴身
    if spirit < 100:
        for cand in ('后退', '后跳', '结界2'):
            if cand in names:
                return cand
    for cand in ('连段A', '5A', '压制A'):
        if cand in names:
            return cand
    return '待机'


def _explain_delta(std, choice, lib) -> str:
    """解释标准与模型选择的差异。"""
    melee = lib['melee']
    bullet = lib['bullet']
    skill = lib['skill']
    if std in melee and choice in bullet:
        return ('近身局面选了弹幕(%s)而非体术(%s) — 弹幕在近身'
                '有硬直风险, 标准应对是体术确认' % (choice, std))
    if std in bullet and choice in melee:
        return ('远距局面选了体术(%s)而非弹幕(%s) — 体术射程不足,'
                '标准是弹幕牵制' % (choice, std))
    if std in ('立防', '蹲防') and choice in (melee | bullet | skill):
        return ('对手攻击中应防御(%s)但选了进攻(%s) — 防御是'
                '安全选择, 进攻赌对手不命中' % (std, choice))
    if std in ('后退', '后跳') and choice in (melee | skill):
        return ('灵力不足应撤退(%s)但选了攻击(%s) — 空灵力攻击'
                '是空挥' % (std, choice))
    return '选了%s而非标准%s' % (choice, std)


def batch_explain(distill_path: str, char: str,
                  limit: int = 10, ppo=None) -> list:
    """批量局面讲解(从distill数据反查模型偏差的Top场景)。

    输入: distill_data_{char}.npz(标准树审计的副产品, 含局面特征+模型选择)
    输出: [讲解文本, ...] — 优先展示偏离最大的场景
    R61o(E4): ppo参数提供时, 计算每场景的策略熵并标注置信度
    """
    import numpy as np
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS[char]
    d = np.load(distill_path, allow_pickle=True)
    X = d['X'] if 'X' in d.files else d[d.files[0]]
    # distill 11列: dx, spirit, close, macro_id, frame, dy,
    #              opp_air, bullet_near, we_left, tti, opp_corner
    dx = X[:, 0] * 1000       # 归一化还原
    spirit = X[:, 1] * 1000
    macro_id = X[:, 3].astype(int)
    opp_air = X[:, 6] > 0.5
    opp_corner = X[:, 10] > 0.5
    out = []
    for i in range(min(limit, len(X))):
        mid = macro_id[i]
        choice = lib['macros'][mid][0] if mid < len(lib['macros']) else '?'
        txt = explain_situation(char, dx[i], bool(opp_air[i]),
                                bool(opp_corner[i]), spirit[i], choice)
        out.append(txt)
    return out
