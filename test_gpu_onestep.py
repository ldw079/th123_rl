# -*- coding: utf-8 -*-
"""从零#2(方法论§6-3): numpy↔GPU一步更新等价探针 — 常驻门禁断言。

从零#2 §3-P2: "前向等价"只在前向/序列化层成立, 一步更新权重不等价
(总体cos 0.99但对手偏置cos≈0、逐张量rel-diff至1.3), 根因四件:
  1) 损失归约sum-vs-mean  2) rstd先除后更  3) 联合梯度裁剪
  4) bc_targets=None幽灵自模仿
本探针: 同权重同批同种子各走一步 → 权重逐张量对比。
四个语义差任一回归 → rel-diff爆到>0.5量级(远超浮点噪声)。
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    try:
        from ppo_gpu import PPOTrainerGPU, HAS_TORCH
    except Exception as e:
        print('跳过: ppo_gpu导入失败 %r' % e)
        return
    if not HAS_TORCH:
        print('跳过: 无torch')
        return
    from ppo import PPOTrainer, CONV_H, CONV_W

    rng = np.random.default_rng(123)
    n_out = 6
    n_side = 5 * n_out + 316

    # GPU侧构造完整权重 → 双向格式保存 → numpy加载(两边严格同权;
    # B4前向等价已钉住save/load保真)
    tmp = tempfile.mkdtemp(prefix='gpu_equiv_')
    pi_p = os.path.join(tmp, 'pi.npz')
    v_p = os.path.join(tmp, 'v.npz')
    gpu_tr = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu_tr.save(pi_p, v_p)
    np_tr = PPOTrainer(n_side=n_side, n_out=n_out)
    np_tr.load(pi_p, v_p)
    gpu_tr.rng = np.random.default_rng(7)
    np_tr.rng = np.random.default_rng(7)     # 同种子同消耗序
    N = 48   # 单minibatch(64内) — 排列顺序无关求和
    feats = rng.integers(0, 255, (N, CONV_H * CONV_W * 3)
                         ).astype(np.uint8)
    sides = rng.standard_normal((N, n_side)).astype(np.float32)
    acts = rng.integers(0, n_out, N).astype(np.int64)
    # rstd敏感批: std≈5(≠初始rstd 1.0) — EMA必须移动(1.0→1.8),
    # "先更后除vs先除后更"产生不同归一化 → 权重分叉(等价修复2钉)
    rews = (rng.standard_normal(N) * 5.0 + 2.0).astype(np.float32)
    masks = np.ones((N, n_out), dtype=bool)
    bc_t = acts.copy()
    opp_next = rng.integers(0, 8, N).astype(np.int64)
    opp_next[-1] = -1

    # numpy保存 → GPU加载(双向格式)
    np_tr.save(pi_p, v_p)
    gpu_tr.load(pi_p, v_p)

    # 各走一步(同参: temp=1.0, 无replay/bc_extra — 首次update池空)
    st_np = np_tr.update(feats, acts, rews, sides, [N],
                         ep_terms=[True], bc_targets=bc_t,
                         masks=masks, opp_next=opp_next, temp=1.0)
    st_gpu = gpu_tr.update(feats, acts, rews, sides, [N],
                           ep_terms=[True], bc_targets=bc_t,
                           masks=masks, opp_next=opp_next, temp=1.0)

    # rstd EMA语义直钉: 先更后除(numpy: _rstd移动1.0→1.8) —
    # 奖励缩放经adv归一化大部分被吸收, 权重差在容差内, 必须直测
    check('rstd EMA同值', abs(np_tr._rstd - gpu_tr._rstd) < 1e-6,
          'np=%.4f gpu=%.4f(先更后除语义)' % (np_tr._rstd, gpu_tr._rstd))

    # 统计字典键对齐
    _np_keys = set(st_np.keys())
    _gpu_keys = set(st_gpu.keys())
    check('统计键对齐', _gpu_keys == _np_keys,
          '缺%s 多%s' % (sorted(_np_keys - _gpu_keys),
                          sorted(_gpu_keys - _np_keys)))

    # 权重逐步对比
    np_tr.save(pi_p, v_p)
    gpu_tr.save(os.path.join(tmp, 'gpi.npz'), os.path.join(tmp, 'gv.npz'))
    d_np = np.load(pi_p)
    d_g = np.load(os.path.join(tmp, 'gpi.npz'))
    worst = ('', 0.0)
    rel_all = {}
    for k in d_np.files:
        if k == 'meta':
            continue
        a, b = d_np[k].astype(np.float64), d_g[k].astype(np.float64)
        if a.shape != b.shape:
            check('形状一致@%s' % k, False, '%s≠%s' % (a.shape, b.shape))
            continue
        denom = np.maximum(np.abs(a) + np.abs(b), 1e-6)
        rel = float((np.abs(a - b) / denom).max())
        rel_all[k] = rel
        if rel > worst[1]:
            worst = (k, rel)
    v_np = np.load(v_p)
    v_g = np.load(os.path.join(tmp, 'gv.npz'))
    for k in v_np.files:
        a, b = v_np[k].astype(np.float64), v_g[k].astype(np.float64)
        denom = np.maximum(np.abs(a) + np.abs(b), 1e-6)
        rel = float((np.abs(a - b) / denom).max())
        rel_all['v:' + k] = rel
        if rel > worst[1]:
            worst = ('v:' + k, rel)

    # 容差分层: 近零参数(conv bias初值0)的浮点噪声可达~0.1; 语义回归
    # (sum↔mean/裁剪/幽灵自模仿)量级0.3-1.3且集中于策略头。判据:
    # ①max<0.12 ②中位<0.01 ③策略头逐键<0.05
    _rel_sorted = sorted(rel_all.values())
    _median = _rel_sorted[len(_rel_sorted) // 2]
    _head = {k: v for k, v in rel_all.items()
             if k in ('W2', 'b2', 'W_side', 'Ws1', 'Ws2', 'bs2',
                      'W_opp', 'Wo1', 'Wo2')}
    check('一步更新权重等价(max)', worst[1] < 0.12,
          '最差 %s rel=%.4f | top3=%s'
          % (worst[0], worst[1],
             sorted(rel_all.items(), key=lambda x: -x[1])[:3]))
    check('一步更新权重等价(中位)', _median < 0.01,
          'median=%.5f' % _median)
    check('策略头精确', max(_head.values()) < 0.05,
          'max=%s' % sorted(_head.items(), key=lambda x: -x[1])[:2])
    # 值路径精确(numpy/GPU值头逐步rel=0的既有结论保持)
    check('KL读数同量级', abs(st_np['kl'] - st_gpu['kl']) < 0.05,
          'np=%.4f gpu=%.4f' % (st_np['kl'], st_gpu['kl']))

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
