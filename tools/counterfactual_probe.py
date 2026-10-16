# -*- coding: utf-8 -*-
"""CE-5阶段一离线探针(2026-10-15): 反事实分歧率仪表 — 策略位置盲区诊断。

方案(capability_extension_plan §CE-5): 决策点对策略top-k宏, 用CE-3
位移表构造"宏后近似状态"(真实core+仅改距离位 — 尽量分布内, 规避
value_rank的OOD教训) → V评估 → 记录"策略选A、反事实认为B优"的分歧率。

**本工具=离线版**(观察期不动训练栈): 在BC库行(专家真实状态+真实视觉栈
X)上测量。迁移窗后在线版挂F6战报(策略自身决策点), 本工具的构造逻辑
(S'手术)届时直接复用。

S'手术(仅距离位, 其余逐位保真):
  - core[2] dx/600 / core[4] adx/600: 新相对距离(位移后)
  - core[5]/[6] own_x/620带: 自身位移后(饱和=位置不可恢复→跳过该行)
  - core[34..42] 位置带one-hot: 按新own_x/adx重算(own带+adx带)
  - core[149]/[150] 贴角标志: 按新坐标重算(1.5幅值口径)
  - 侧向量射程差块[2n+CORE:3n+CORE]: clip((adx'−reach_i)/200)×mask_i
    (mask_i与状态无关, 与train_tm._build_side同源重算)
  - 不改: 视觉X(保持真实 — 方案明示"真实core"精神)、ady块、untech块
    (保守: 只动距离位)

位移口径: 挖掘经mirror_frames规范到"施招者在左朝右" — 世界系dx =
sign × 表均值, sign=+1当对手在我右侧。命中桶(dx_opp_hit)+dx_self。
低置信/无样本宏 → 无反事实(跳过该宏, 不造数据)。

用法:
  python tools/counterfactual_probe.py --char reimu [--rows 2000]
      [--topk 3] [--seed 7] [--json out.json]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE_DIR = os.environ.get('TH123_STORE', r'D:\temp\th123_models')

# core布局锚(R138b实证): [2]=dx/600 [4]=adx/600 [5]=own_x/620
# [6]=1-own_x/620 [10]=air [34..36]=own带 [39..42]=adx带
# [149]=opp贴角 [150]=own贴角(值1.5)
C_DX, C_ADX, C_OX, C_OXI = 2, 4, 5, 6
C_OWNBAND, C_ADXBAND, C_OPPCORNER, C_OWNCORNER = 34, 39, 149, 150
FIELD_W = 1280.0


def load_policy(char):
    """生产fleet模型 → (PPOTrainer, n_macros)。复用side_driver同构加载。"""
    from feat_builder import FeatureBuilder
    from train_tm import CHAR_LIBS
    from ppo import PPOTrainer
    n_macros = len(CHAR_LIBS[char]['names'])
    # n_side须显式(类默认锚定reimu宏数 — marisa/suika会撞维度)
    pi = PPOTrainer(n_side=5 * n_macros + FeatureBuilder.CORE_DIMS,
                    n_out=n_macros)
    path = os.path.join(STORE_DIR, 'model_ppo_%s_fleet.npz' % char)
    pi.load(path, path.replace('.npz', '') + '_v.npz')
    return pi, n_macros


def load_disp(char, n_macros, lib_names):
    """宏→(dx_opp_hit, dx_self)位移数组(None=无反事实)。

    映射链复用reach_maps管线: 宏名→CHAR_MACRO_MOVES→action IDs→
    位移表(多ID取首个高置信; 低置信→None, R24保守门同款)。
    """
    sys.path.insert(0, ROOT)
    from reach_maps import CHAR_MACRO_MOVES
    p = os.path.join(ROOT, 'data', 'move_displacement_%s.json' % char)
    if not os.path.exists(p):
        return None, None
    tab = json.load(io.open(p, encoding='utf8'))['actions']
    moves = CHAR_MACRO_MOVES.get(char, {})
    dxo = np.full(n_macros, np.nan)
    dxs = np.full(n_macros, np.nan)
    for i, name in enumerate(lib_names):
        mids = moves.get(name)
        if not mids:
            continue
        for mid in mids:
            e = tab.get(str(mid))
            if not e or e.get('low_confidence'):
                continue
            h = e.get('dx_opp_hit') or {}
            s = e.get('dx_self') or {}
            if h.get('n', 0) >= 10 and s.get('n', 0) >= 10:
                dxo[i] = float(h['mean'])
                dxs[i] = float(s['mean'])
                break
    return dxo, dxs


def recover_positions(core):
    """从core行恢复(own_x, dx)。饱和(clip边界)→None=不可恢复。"""
    ox_n, oxi_n = float(core[C_OX]), float(core[C_OXI])
    dx_n = float(core[C_DX])
    if ox_n >= 1.0 - 1e-6 or oxi_n >= 1.0 - 1e-6 or abs(dx_n) >= 1.0 - 1e-6:
        return None        # own_x≥620 / dx≥600 → 像素不可精确恢复
    own_x = ox_n * 620.0
    dx = dx_n * 600.0
    return own_x, dx


def surgery(S, sign, push_opp, move_self, reach, reach_mask, n):
    """S(1,n_side) → S' 仅改距离位。返回None=位置不可恢复。"""
    core_off = 2 * n
    Sp = S.copy()
    s = Sp[0]                                # 行视图(一维手术)
    pos = recover_positions(s[core_off:core_off + 358])
    if pos is None:
        return None
    own_x, dx = pos
    own_x2 = float(np.clip(own_x + sign * move_self, 0.0, FIELD_W))
    dx2 = float(np.clip(dx + sign * push_opp - sign * move_self,
                        -600.0, 600.0))
    adx2 = abs(dx2)
    opp_x2 = own_x2 + dx2

    c = core_off
    s[c + C_DX] = np.clip(dx2 / 600.0, -1, 1)
    s[c + C_ADX] = np.clip(adx2 / 600.0, 0, 1)
    if own_x2 <= 620.0:
        s[c + C_OX] = own_x2 / 620.0
        s[c + C_OXI] = 1.0 - own_x2 / 620.0
    # own位置带(<350/350-850/>850, 值1.5)
    b = 0 if own_x2 < 350 else (1 if own_x2 < 850 else 2)
    s[c + C_OWNBAND:c + C_OWNBAND + 3] = 0.0
    s[c + C_OWNBAND + b] = 1.5
    # adx带((0,130)(130,250)(250,450)(450,1300))
    ab = next(i for i, (lo, hi) in enumerate(
        [(0, 130), (130, 250), (250, 450), (450, 1e9)]) if lo <= adx2 < hi)
    s[c + C_ADXBAND:c + C_ADXBAND + 4] = 0.0
    s[c + C_ADXBAND + ab] = 1.5
    # 贴角标志(120/1120口径, 值1.5)
    s[c + C_OPPCORNER] = 1.5 if (opp_x2 < 120 or opp_x2 > 1120) else 0.0
    s[c + C_OWNCORNER] = 1.5 if (own_x2 < 120 or own_x2 > 1120) else 0.0
    # 射程差块(与train_tm._build_side同式)
    b0 = core_off + 358
    s[b0:b0 + n] = (np.clip((adx2 - reach) / 200.0, -1, 1)
                    * reach_mask).astype(np.float32)
    return Sp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--rows', type=int, default=2000)
    ap.add_argument('--topk', type=int, default=3)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    from bc_io import load_bank
    from train_tm import CHAR_LIBS
    from reach_maps import resolve_reach

    pi, n = load_policy(args.char)
    lib = CHAR_LIBS[args.char]
    names = lib['names']
    reach, reach_v = resolve_reach(lib['macros'], args.char)
    # mask同train_tm口径: reach>0 且攻击宏(_atk_idx=非防御/非SC预备)
    # 简化: reach>0即门(保守 — 比生产mask略宽不入特征只入探针)
    reach_mask = (reach > 0).astype(np.float32)
    dxo, dxs = load_disp(args.char, n, names)

    X, S, _Y = load_bank(args.char, store=STORE_DIR)
    rng = np.random.default_rng(args.seed)
    idx = rng.choice(len(S), size=min(args.rows, len(S)), replace=False)
    Xs = np.asarray(X[idx], dtype=np.float32).reshape(-1, 3, 60, 80) / 255.0
    Xs = Xs.reshape(len(idx), -1)          # _trunk吃(N,14400)
    Ss = np.asarray(S[idx], dtype=np.float32)
    print('样本 %d行(BC库%d) | 位移覆盖宏 %d/%d' % (
        len(idx), len(S), int(np.isfinite(dxo).sum()), n))

    # 策略分布 + trunk(一次前向)
    Xn, _, P = pi._pi_forward(Xs, Ss, temp=1.0)
    topk = np.argsort(-P, axis=1)[:, :args.topk]

    # 基线V(真实状态)
    _, V_real, _ = pi._v_forward(Xn, Ss)
    V_real = np.asarray(V_real).ravel()

    n_div = n_cf = n_skip_pos = n_skip_disp = 0
    margin_sum = 0.0
    examples = []
    for r in range(len(idx)):
        ks = [k for k in topk[r] if np.isfinite(dxo[k])]
        if not ks:
            n_skip_disp += 1
            continue
        # sign: 对手在我右→+1(施招者朝右规范)
        core_off = 2 * n
        dx = float(Ss[r, core_off + C_DX]) * 600.0
        sign = 1.0 if dx >= 0 else -1.0
        cands = []
        for k in ks:
            Sp = surgery(Ss[r:r + 1].copy(), sign, dxo[k], dxs[k],
                         reach, reach_mask, n)
            if Sp is None:
                continue
            _, v, _ = pi._v_forward(Xn[r:r + 1], Sp)
            cands.append((float(v.ravel()[0]), int(k)))
        if len(cands) < 2:
            n_skip_pos += 1
            continue
        n_cf += 1
        v_best = max(cands)
        # 策略首选 = topk中首个有位移覆盖的宏(与V-最优同候选集比较)
        pol_first = next((int(k) for k in topk[r] if k in ks), None)
        if pol_first is None:
            continue
        if v_best[1] != pol_first:
            n_div += 1
            margin_sum += (v_best[0] - min(
                v for v, k in cands if k == pol_first))
            if len(examples) < 12:
                examples.append({
                    'row': int(idx[r]), 'policy': names[pol_first],
                    'cf_best': names[v_best[1]],
                    'v_gap': round(v_best[0] - dict(
                        (k, v) for v, k in cands)[pol_first], 4),
                    'adx': round(abs(dx), 1),
                })

    rate = n_div / max(1, n_cf)
    print('\n===== 反事实分歧率(CE-5阶段一离线版) =====')
    print('有效反事实行: %d / %d (跳过: 无位移宏%d 位置饱和%d)'
          % (n_cf, len(idx), n_skip_disp, n_skip_pos))
    print('分歧率: %.1f%% (策略首选 ≠ V-最优)' % (100 * rate))
    if n_div:
        print('平均V差(分歧行): %.4f' % (margin_sum / n_div))
    print('示例(前12):')
    for e in examples:
        print('  row%-7d 策略=%-10s 反事实优=%-10s ΔV=%.4f adx=%.0f'
              % (e['row'], e['policy'], e['cf_best'], e['v_gap'], e['adx']))
    if args.json:
        out = {'char': args.char, 'rows': len(idx), 'topk': args.topk,
               'n_cf': n_cf, 'divergence_rate': rate,
               'mean_v_gap': (margin_sum / n_div) if n_div else 0.0,
               'examples': examples,
               'note': '离线BC库行; 在线版待迁移窗挂F6'}
        io.open(args.json, 'w', encoding='utf8').write(
            json.dumps(out, ensure_ascii=False, indent=1))
        print('→ %s' % args.json)


if __name__ == '__main__':
    main()
