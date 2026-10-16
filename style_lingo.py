# -*- coding: utf-8 -*-
"""S-7C(合并终版方案): 风格嵌入→自然语言投影(投影≠定义).

教学讲解的风格描述接口: 从可解释的原始轴(非PCA黑盒)生成短语 —
PCA主成分保留给特征侧, 人类可读的解释走语义明确的维度。
teach.py消费; 也可供S-7B审计残差的定性归因。
"""
from __future__ import annotations


def describe_style(opp_feats75, style_emb=None) -> str:
    """对手风格短语(分号分隔的轴描述)。

    opp_feats75: OpponentModel.features()输出 — 轴位与FEAT_NAMES对齐:
      [8]=跳频 [12]=低灵帧 [13]=射击帧 [20]=漂移
      [21+5*8+0..3]=灵满防/攻/射/机 [21+40+0..3]=灵空四类
    style_emb: 可选16维嵌入(补充漂移维度语义)。
    """
    if opp_feats75 is None or len(opp_feats75) < 75:
        return '风格未知'
    f = opp_feats75
    parts = []
    # 跳频(EMA计数, ~每秒62帧标度)
    jump = float(f[8])
    parts.append('频繁起跳' if jump > 8 else (
        '很少起跳' if jump < 1.5 else '起跳适中'))
    # 射击倾向
    bullet = float(f[13])
    parts.append('弹幕压制型' if bullet > 12 else (
        '近身缠斗型' if bullet < 3 else '弹幕近身均衡'))
    # 稳健度: 情境防 vs 攻(当前情境行的防/攻占比)
    guard_share = float(f[0])
    attack_share = float(f[1])
    if guard_share + attack_share > 1e-6:
        ratio = guard_share / (guard_share + attack_share)
        parts.append('稳健防御' if ratio > 0.6 else (
            '激进压制' if ratio < 0.3 else '攻防均衡'))
    # 漂移(风格变化率)
    drift = float(f[20]) if len(f) > 20 else 0.0
    if style_emb is not None and len(style_emb) >= 9:
        drift = max(drift, float(style_emb[8]))
    parts.append('风格多变' if drift > 0.5 else '风格稳定')
    # 资源条件化: 灵空时的防御占比(灵空还敢攻=资源依赖激进)
    _low_g = 21 + 40
    low_guard, low_attack = float(f[_low_g]), float(f[_low_g + 1])
    if low_guard + low_attack > 1e-6:
        if low_attack / (low_guard + low_attack) > 0.5:
            parts.append('低灵仍激进(资源依赖)')
    return '; '.join(parts)


def style_advice(opp_feats75, style_emb=None) -> str:
    """风格应对提示(教学短语 — 投影生成的建议, 非硬规则)."""
    if opp_feats75 is None or len(opp_feats75) < 75:
        return ''
    f = opp_feats75
    jump = float(f[8])
    bullet = float(f[13])
    tips = []
    if jump > 8:
        tips.append('对手爱跳 — 对空准备(jA/623B)值得常备')
    if bullet > 12:
        tips.append('对手弹幕密 — 高跳GRAZE穿弹或结界推进')
    guard_share = float(f[0])
    attack_share = float(f[1])
    if guard_share + attack_share > 1e-6 and \
            guard_share / (guard_share + attack_share) > 0.6:
        tips.append('对手偏防 — 磨灵(弹幕)/择(中下段)比强攻有效')
    return '; '.join(tips)
