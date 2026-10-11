# -*- coding: utf-8 -*-
"""阶段0(系列预测方案§2) 配对测试: series_meter 两仪表(合成序列).

覆盖(方案§2门禁要求"两仪表各配一条行为断言+变异"):
  1. 胜负解码: 回合结算块(≥+3胜/≤-5负, 先胜2定局) — W/L/噪声三态
  2. 系列位置: ep%5+1 → 1..5(轮换周期=系列长, 方案§3.1口径)
  3. 分桶: b1/b2/b3/b4-5 映射
  4. aux评分路径: 真PPOTrainerGPU前向(no_grad), 构造50%命中可复现
  5. 曲线行: 合成记录 → 四桶全非空 + 命中率/胜率数值正确
"""
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from series_meter import (BUCKETS, aux_predict, bucket_of,
                          curve_line, decode_match_outcome,
                          position_from_meta, score_episode_aux,
                          series_position)

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def main():
    # --- 1. 胜负解码 ---
    ok(decode_match_outcome([8.0, -6.0, 12.0]) == 'W',
       "解码W: 2胜回合1负回合")
    ok(decode_match_outcome(np.array([-7.0, 0.2, -8.0])) == 'L',
       "解码L: 2负回合(微收入噪声0.2不干扰)")
    ok(decode_match_outcome([0.3, 0.1, -0.5]) == '?',
       "解码?: 纯势函数噪声无结算块")

    # --- 2/3. 系列位置与分桶 ---
    ok([series_position(e) for e in (0, 3, 4, 5, 9)] == [1, 4, 5, 1, 5],
       "位置=ep%5+1(轮换组内序位)")
    ok([bucket_of(p) for p in (1, 2, 3, 4, 5)]
       == ['b1', 'b2', 'b3', 'b4-5', 'b4-5'], "分桶映射b1/b2/b3/b4-5")
    ok(position_from_meta({'match_in_series': 3, 'ep': 99}) == 3
       and position_from_meta({'match_in_series': 15, 'ep': 0}) == 5
       and position_from_meta({'ep': 7}) == 3
       and position_from_meta({}) == 1,
       "position_from_meta: match_in_series优先(钳5) 回退ep%5+1")

    # --- 4. aux评分路径(真前向) ---
    try:
        from ppo_gpu import PPOTrainerGPU
    except ImportError:
        print("[SKIP] torch不可用 — aux路径以解码/分桶断言为准")
    else:
        n_out, n_side = 8, 5 * 8 + 330
        tr = PPOTrainerGPU(n_side=n_side, n_out=n_out)
        if hasattr(tr, 'init_fresh'):
            tr.init_fresh(3 * 60 * 80)
        N = 24
        rng = np.random.default_rng(7)
        feats = rng.integers(0, 255, size=(N, 14400), dtype=np.uint8)
        sides = rng.standard_normal((N, n_side)).astype(np.float32)
        masks = np.ones((N, n_out), dtype=np.float32)
        preds = aux_predict(tr.net, feats, sides, masks, tr._temp)
        ok(len(preds) == N and preds.min() >= 0 and preds.max() < n_out,
           "aux_predict批前向输出N行类号")
        # 构造50%命中: 偶数行=预测本身, 奇数行=偏移类
        opp = preds.copy()
        opp[1::2] = (preds[1::2] + 1) % n_out
        arr = {'feats': feats, 'sides': sides, 'masks': masks,
               'opp_next': opp}
        h, n = score_episode_aux(tr.net, arr, tr._temp)
        ok(n == N and h == N // 2,
           "score_episode_aux=50%命中(可复现构造)")
        arr_com = dict(arr, opp_next=np.full(N, -1, dtype=np.int64))
        h2, n2 = score_episode_aux(tr.net, arr_com, tr._temp)
        ok((h2, n2) == (0, 0), "COM局(标签全-1)→(0,0)不入aux分母")

    # --- 5. 曲线行 ---
    recs = [
        (1, 30, 100, 'W'), (1, 20, 100, 'L'), (1, None, 0, 'W'),
        (2, 45, 100, 'W'), (2, 45, 100, 'W'),
        (3, 60, 50, 'L'),
        (4, 80, 100, 'W'), (4, 70, 100, 'W'), (4, 90, 100, 'W'),
        (5, None, 0, 'L'),
    ]
    line = curve_line(recs)
    ok(all(('b%d' % i if i <= 3 else 'b4-5') in line for i in (1, 2, 3))
       and 'b4-5' in line, "曲线行四桶全非空")
    ok('b1:aux25%(n200)' in line and 'W2-1(67%)' in line,
       "b1命中率=50/200=25%% 胜率2/1=67%%")
    ok('b2:aux45%(n200) W2-0(100%)' in line, 'b2数值')
    ok('b4-5:aux80%(n300) W3-1(75%)' in line, 'b4-5聚合(4+5位)')

    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
