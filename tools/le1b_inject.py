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


def inject_count(k):
    """k行采样中注入行数(向上取整但不超过k*INJECT_RATIO)."""
    if INJECT_RATIO <= 0:
        return 0
    return min(int(np.ceil(k * INJECT_RATIO)), int(k * INJECT_RATIO))


def inject_indices(char, k, rng):
    """从情境库选k个行索引(热度加权, 对位/贴角/近距/攻击偏好).

    参数k=目标注入行数(调用方已算好inject_count, 此处不再衰减 —
    首版双重inject_count致12→2行, 已修).
    返回: BC库行索引array(可空) 或 None(库缺/不足).
    """
    if k <= 0:
        return None
    from situation_library import query
    idx = query(char, attack=True, near=True, k=0,
                heat_weighted=True)
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
