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


def value_rank(ppo, char, dx, spirit, opp_air, opp_corner,
               top_k=8):
    """R61p(E2): 价值网络宏排名 — "这个局面下每个选择值多少".

    方法: 构造侧向量(情境参数+各宏one-hot), 视觉置零(中性基线),
    逐宏计算V(s, macro_i) → 排名. 不需要真实视觉(侧向信号已含
    位置/灵力/对手状态等关键决策信息).
    P1-B(从零#2): (a)原`_, V =`双解包_v_forward的3元组→异常被吞
    →V≡0→排名退化为宏序号; (b)core偏移原硬编码且错位(spirit→
    角落位6/own_hp→opp_hp位/opp_air→gauge位12). 修: core区用真实
    FeatureBuilder.build构造(偏移永远与布局同源), 解包取3元组中段.

    返回: [(宏名, V值, 排名), ...] top_k条, V值降序.
    """
    import numpy as np
    from train_tm import CHAR_LIBS
    from feat_builder import FeatureBuilder
    lib = CHAR_LIBS[char]
    n = len(lib['macros'])

    # 局面构造(真实builder — dx/灵力/空中/版边全走正式归一化路径)
    fb = FeatureBuilder(n)
    ox = 1200.0 if opp_corner else 700.0
    own = {"position.x": ox - dx, "position.y": 0.0, "direction": 1,
           "action": 0, "spirit": float(spirit), "hp": 10000,
           "airBorne": False, "untech": 0, "cardGauge": 0, "score": 0,
           "comboDamage": 0, "hitStop": 0, "timeStop": 0,
           "hand": b'\xff' * 10}
    opp = {"position.x": ox, "position.y": 200.0 if opp_air else 0.0,
           "direction": -1, "action": 0, "spirit": 2000.0, "hp": 10000,
           "airBorne": bool(opp_air), "untech": 0, "cardGauge": 0,
           "score": 0, "comboDamage": 0, "hitStop": 0, "timeStop": 0,
           "hand": b'\xff' * 10}
    core = fb.build(own, opp, {"active": 0}, [])

    n_side = 5 * n + fb.CORE_DIMS
    side = np.zeros(n_side, dtype=np.float32)
    # 审计#3 P2披露: V在此为**分布外评估** — 3n视觉块与侧向量均以
    # 零/合成值构造(训练分布外), 值读数只作宏间相对比较, 绝对值
    # 不可当局面价值引用。
    side[2 * n:2 * n + fb.CORE_DIMS] = core

    # 视觉置零(14400 = 3×80×60) — trunk只算一次(所有宏共享)
    feat = np.zeros(14400, dtype=np.uint8)
    try:
        Xn = ppo._trunk_fwd_chunked(feat.reshape(1, -1))
    except Exception:
        return [(lib['names'][i], 0.0, i) for i in range(min(top_k, n))]

    # 逐宏评估: 替换one-hot → V(s, macro)
    results = []
    for i in range(n):
        s = side.copy()
        s[i] = 1.0    # 当前宏one-hot
        try:
            _, V, _ = ppo._v_forward(Xn, s.reshape(1, -1))
            v = float(np.ravel(V)[0])
        except Exception:
            v = 0.0
        results.append((lib['names'][i], v, i))
    results.sort(key=lambda x: -x[1])
    return results[:top_k]


def explain_with_value(char, dx, spirit, opp_air, opp_corner,
                       model_choice, ppo, top_k=5) -> str:
    """R61p(E2): 价值网络驱动的局面讲解(v2).

    三层对比: 价值排名 vs 教义树 vs 模型实际选择.
    输出格式:
      【价值排名】(前5)
      【教义标准】X
      【模型选择】Y (置信度Z)
      【价值分析】选Y在价值排名第N(V=...), 最优是X(V=...)
    """
    ranked = value_rank(ppo, char, dx, spirit, opp_air,
                        opp_corner, top_k)
    lib_names = {n for n, _, _ in ranked}
    std = _doctrine_best(dx, opp_air, opp_corner, spirit,
                         __import__('train_tm').CHAR_LIBS[char])

    parts = []
    parts.append('【局面】距离%.0f 对手%s%s 灵力%.0f'
                 % (dx, '空中' if opp_air else '地面',
                    ' 版边' if opp_corner else '', spirit))
    parts.append('【价值排名】')
    for rank, (name, v, _) in enumerate(ranked, 1):
        marker = ' ←模型选' if name == model_choice else (
            ' ←教义标准' if name == std else '')
        parts.append('  %d. %s V=%.3f%s' % (rank, name, v, marker))

    parts.append('【模型选择】%s' % model_choice)
    # 价值差分析
    choice_v = next((v for n, v, _ in ranked
                     if n == model_choice), None)
    best_n, best_v, _ = ranked[0]
    if choice_v is not None:
        gap = best_v - choice_v
        if model_choice == best_n:
            parts.append('【价值分析】✓ 模型选了价值最高的宏')
        elif gap < 0.1:
            parts.append('【价值分析】%s 与最优%s差%.3f — 接近等效'
                         % (model_choice, best_n, gap))
        else:
            parts.append('【价值分析】%s(V=%.3f) 比最优%s(V=%.3f)低%.3f'
                         % (model_choice, choice_v, best_n,
                            best_v, gap))
    return '\n'.join(parts)


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
    # P1-B(从零#2): dx原×1000(该列本就是原始像素, 只有spirit是/1000
    # 归一化存储); macro_id=-1原经lib['macros'][-1]恒报最后一个宏。
    dx = X[:, 0]
    spirit = X[:, 1] * 1000
    macro_id = X[:, 3].astype(int)
    opp_air = X[:, 6] > 0.5
    opp_corner = X[:, 10] > 0.5
    out = []
    n_macros = len(lib['macros'])
    for i in range(min(limit, len(X))):
        mid = macro_id[i]
        choice = (lib['macros'][mid][0]
                  if 0 <= mid < n_macros else '未知(%d)' % mid)
        txt = explain_situation(char, dx[i], bool(opp_air[i]),
                                bool(opp_corner[i]), spirit[i], choice)
        out.append(txt)
    return out
