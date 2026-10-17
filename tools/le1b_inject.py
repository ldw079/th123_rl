# -*- coding: utf-8 -*-
"""LE-1b(学习效率方案v2§LE-1b): 情境注入激活 — 高价值情境优先入BC-extra.

设计(方案口径):
  注入通道: bc_extra(既有BC锚通道的扩展) — 在_sample_bc的64行采样中,
  一部分行从情境库按热度加权选取(替代纯iid), 使高价值情境(弱点对位
  的攻击/贴角/近距)获得更高的模仿梯度密度.
  **注入混合比上限: ≤20% 批占比**(方案v2硬约束 — 防回放分布偏离
  策略分布过远, 重要性失配); 专项A/B验证.
  通道选择: bc_extra优先(与BC锚同机制, 零新通道); distill/tm_env快照
  为二期.

实现: 本模块被train_tm._sample_bc和learner_hub.update_from_episodes
调用, 提供inject_rows(char, k) → (X_idx, S_idx, Y_idx)或None.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

# 注入比(0.0=关, 方案上限0.20)
INJECT_RATIO = float(os.environ.get('TH123_LE1B_RATIO', '0.0'))
OUT_DIR = os.path.join(ROOT, 'data', 'situations')


# LE-1b硬上限(方案v2): 注入行数不得超过批的 20% — 防回放分布离策略过远。
INJECT_CAP = 0.20


def inject_count(k):
    """k行批中注入行数 — 比例先钳到 INJECT_CAP(20%), 再向下取整。

    P1-15(从零#5): 原 min(ceil(k*r), int(k*r)) 对 r=0.5/1.0 分别给出
    32/64(占批 50%/100%), 20% 上限从未生效。
    """
    if INJECT_RATIO <= 0 or k <= 0:
        return 0
    eff = min(INJECT_RATIO, INJECT_CAP)
    return int(np.floor(k * eff))


def _weakest_matchup(char):
    """情境库 meta 里热度最高(最弱)的对位池槽 — 无 heat 返回 None。

    P1-3(从零#5): 原实现**从不传 matchup** → query 内
    `if heat_weighted and matchup is not None` 恒假, 热度分支从不执行
    (实测返回全量 66,940 行 = 无热度)。修=取最弱对位传入。
    """
    import json as _json
    import situation_library as _sl
    # 运行时取 OUT_DIR(不在 import 期绑定 — R109 教训: 定义时绑定使 patch 失效)
    p = os.path.join(_sl.OUT_DIR, '%s_index.npz' % char)
    if not os.path.exists(p):
        return None
    try:
        meta = _json.loads(str(np.load(p, allow_pickle=True)['meta']))
        heat = meta.get('heat', {})
        if not heat:
            return None
        return int(max(heat, key=lambda k: heat[k]))
    except (OSError, ValueError, KeyError):
        return None


def inject_indices(char, k, rng, matchup=None):
    """从情境库选k个行索引(热度加权, 对位/贴角/近距/攻击偏好).

    参数k=目标注入行数(调用方已算好inject_count, 此处不再衰减 —
    首版双重inject_count致12→2行, 已修).
    matchup: 对位池槽; None=自动取热度最高(最弱)对位。
    返回: BC库行索引array(可空) 或 None(库缺/不足).
    """
    if k <= 0:
        return None
    from situation_library import query
    if matchup is None:
        matchup = _weakest_matchup(char)
    idx = query(char, matchup=matchup, attack=True, near=True, k=0,
                heat_weighted=True)
    if idx is None or len(idx) < k:
        # 热度过滤后可能不足k行 → 退回不加权的同情境集合(不空手而归)
        idx = query(char, matchup=matchup, attack=True, near=True, k=0,
                    heat_weighted=False)
    if idx is None or len(idx) < k:
        return None
    sel = rng.choice(len(idx), size=k, replace=False)
    return idx[sel]


def main():
    """CLI: 状态查询/手动注入比设置验证."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--ratio', type=float, default=None,
                    help='测试: 给定比算注入行数')
    ap.add_argument('--sample', type=int, default=64,
                    help='模拟采样批大小')
    a = ap.parse_args()
    global INJECT_RATIO
    if a.ratio is not None:
        INJECT_RATIO = a.ratio
    print('注入比: %.1f%% (env TH123_LE1B_RATIO=%s)'
          % (100 * INJECT_RATIO,
             os.environ.get('TH123_LE1B_RATIO', '未设(默认关)')))
    n = inject_count(a.sample)
    print('  %d行批 → 注入%d行' % (a.sample, n))
    if n > 0:
        rng = np.random.default_rng(42)
        idx = inject_indices(a.char, n, rng)
        if idx is not None:
            print('  实际选到: %d行(情境库query)' % len(idx))
        else:
            print('  情境库query返回None(库缺或不足)')


if __name__ == '__main__':
    main()
