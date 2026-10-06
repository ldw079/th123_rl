# -*- coding: utf-8 -*-
"""R61s(F6): 380 matchup评估体系 — 20角色全矩阵战报.

设计(主规划§1-F6):
  20×20 − 20(自身) = 380 对局配对. 每配对N局 → 胜率矩阵 → 分析:
  - 每角色综合胜率(横排平均) = 角色强度排名
  - 最大克星(最差对位) / 最易对手(最佳对位)
  - 超人距离度量: 平均胜率 vs 胜率标准差(高均值+低方差=全面强)

  评估用SideDriver(确定性, 温度跟随模型退火值) — 与训练行为策略
  一致(不是冷静1.0采样), 战报不低估.

用法: python tools/eval_matrix.py [--chars 3] [--games 2] [--full]
  --chars 3  = 只评三现役(快速)
  --chars 20 = 全20角色(完整, 需所有角色模型)
  --full     = 完整380配对(否则只评三角循环)
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')

ALL_CHARS = ['reimu', 'marisa', 'suika', 'sakuya', 'patchouli',
             'yuyuko', 'reisen', 'komachi', 'tenshi', 'alice',
             'youmu', 'remilia', 'yukari', 'aya', 'iku',
             'sanae', 'cirno', 'meiling', 'utsuho', 'suwako']


def has_model(char):
    return os.path.exists(os.path.join(
        STORE, 'model_ppo_%s.npz' % char))


def available_chars(n):
    if n <= 3:
        return ['reimu', 'marisa', 'suika']
    return [c for c in ALL_CHARS if has_model(c)][:n]


def run_matchup(char_a, char_b, port, games=2, tps=480):
    """一对角色的评估对局(A=模型驱动, B=模型驱动).

    返回: {'a_wins': x, 'b_wins': y, 'games': n}
    P0-C(从零#2): 原三病 — (a)死行引用未定义last_state+frame_input
    .__wrapped__(不存在)双双被except:pass吞 → 每场0-0(全矩阵是对
    零矩阵的排名); (b)用TMEnv而非EvalEnv → last_match恒None;
    (c)每循环step两次=输入隔帧送达(宏帧计时 减半)。修: EvalEnv+
    上一拍输入保持的单步节律(与训练循环同构)+异常显式计数。
    """
    from train_tm import CHAR_LIBS  # noqa: F401 (lib检查)
    from side_driver import SideDriver, EvalEnv

    # 双方都用SideDriver(确定性评估)
    driver_a = SideDriver(char_a, 'L')
    driver_b = SideDriver(char_b, 'R')
    driver_a.load(os.path.join(STORE, 'model_ppo_%s.npz' % char_a))
    driver_b.load(os.path.join(STORE, 'model_ppo_%s.npz' % char_b))

    a_wins = 0
    b_wins = 0
    for g in range(games):
        env = EvalEnv(port, char_left=char_a, char_right=char_b,
                      vs_com=False, tps=tps)
        inp_a, inp_b = {}, {}
        _sl = _sr = 0          # 回合比分追踪(顶时判定用)
        try:
            # F6缺口修复(2026-10-07): ①胜局检查必须在r is None break
            # **之前** — GameEnded被step吞掉返回None, 但EvalEnv._rec
            # 已记录last_match, 原顺序在读取前就退出(每对0W-0L根因);
            # ②帧上限12000<一整场(3回合顶时≈18.4k+开销) — 提到45000;
            # ③顶时口径: 上限到时按回合比分判胜(比分同→HP差, 再同不计)
            for frames in range(45000):
                r = env.step(inp_a, inp_b)
                if env.last_match:
                    _w, ls, rs = env.last_match
                    if ls > rs:
                        a_wins += 1
                    else:
                        b_wins += 1
                    env.last_match = None
                    break
                if r is None:
                    break
                left, right, weather, objs = r
                _sl, _sr = left.get("score", 0), right.get("score", 0)
                if frames < 60:      # intro排水
                    continue
                inp_a = driver_a.frame_input(left, right, weather,
                                             objs, [])
                inp_b = driver_b.frame_input(right, left, weather,
                                             objs, [])
            else:
                if _sl != _sr:
                    if _sl > _sr:
                        a_wins += 1
                    else:
                        b_wins += 1
                    print('  [eval] 顶时判定: 回合比分%d-%d' % (_sl, _sr))
                elif left.get("hp", 0) != right.get("hp", 0):
                    if left["hp"] > right["hp"]:
                        a_wins += 1
                    else:
                        b_wins += 1
                    print('  [eval] 顶时判定: 比分平, HP差判')
                else:
                    print('  [eval] 顶时且无比分/HP差 — 不计')
        except Exception as e:
            print('  [eval] %s vs %s 第%d局异常(%s: %s) — 该局不计'
                  % (char_a, char_b, g + 1, type(e).__name__, e))
        finally:
            try:
                env.close()
            except Exception:
                pass

    return {'a_wins': a_wins, 'b_wins': b_wins, 'games': games}


def build_matrix(chars, games=2, full=False):
    """构建胜率矩阵."""
    n = len(chars)
    matrix = {}
    pairs = list(itertools.combinations(range(n), 2)) if full \
        else [(i, j) for i in range(n) for j in range(i + 1, n)]
    print('配对数: %d (角色%d, 每对%d局)' % (len(pairs), n, games))
    for idx, (i, j) in enumerate(pairs):
        ca, cb = chars[i], chars[j]
        print('[%d/%d] %s vs %s...' % (idx + 1, len(pairs), ca, cb))
        port = 20900 + (idx % 10)   # eval段端口
        result = run_matchup(ca, cb, port, games)
        key = '%s|%s' % (ca, cb)
        matrix[key] = result
        wr = result['a_wins'] / max(result['games'], 1)
        print('  %s %.0f%% (%dW-%dL)' % (
            ca, wr * 100, result['a_wins'], result['b_wins']))
    return matrix


def analyze(matrix, chars):
    """分析矩阵 → 排名/克星/超人距离."""
    n = len(chars)
    wins = {c: [] for c in chars}
    for key, r in matrix.items():
        ca, cb = key.split('|')
        wr = r['a_wins'] / max(r['games'], 1)
        wins[ca].append(('win', wr))
        wins[cb].append(('lose', 1 - wr))

    report = {'ranking': [], 'matrix_size': len(matrix)}
    for c in chars:
        if not wins[c]:
            continue
        rates = [r for _, r in wins[c]]
        avg = sum(rates) / len(rates)
        var = sum((r - avg) ** 2 for r in rates) / len(rates) if rates else 0
        report['ranking'].append({
            'char': c, 'avg_wr': avg, 'var': var,
            'games': len(rates),
        })
    report['ranking'].sort(key=lambda x: -x['avg_wr'])

    # 超人距离: 高平均胜率+低方差 = 全面强(超人特征)
    if report['ranking']:
        top = report['ranking'][0]
        report['superhuman_distance'] = {
            'top_char': top['char'],
            'top_wr': top['avg_wr'],
            'top_var': top['var'],
            'metric': top['avg_wr'] - top['var'],
            'note': '高均值-低方差=全面强; metric=%.3f(越高越接近超人)'
                    % (top['avg_wr'] - top['var']),
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', type=int, default=3)
    ap.add_argument('--games', type=int, default=2)
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--output', default=None)
    args = ap.parse_args()

    chars = available_chars(args.chars)
    print('评估角色: %s' % chars)
    print('可用模型: %d/%d' % (len(chars), args.chars))

    matrix = build_matrix(chars, args.games, args.full)
    report = analyze(matrix, chars)

    print('\n=== 排名 ===')
    for i, r in enumerate(report['ranking'], 1):
        print('%2d. %-10s 胜率%.1f%% 方差%.3f (%d局)'
              % (i, r['char'], r['avg_wr'] * 100, r['var'],
                 r['games']))
    if 'superhuman_distance' in report:
        sd = report['superhuman_distance']
        print('\n=== 超人距离 ===')
        print('  最强: %s (胜率%.1f%% 方差%.3f 指标%.3f)'
              % (sd['top_char'], sd['top_wr'] * 100, sd['top_var'],
                 sd['metric']))

    out = args.output or os.path.join(
        HERE, 'eval_matrix_%s_%s.json'
        % ('full' if args.full else 'quick',
           time.strftime('%Y%m%d')))
    with open(out, 'w', encoding='utf8') as f:
        json.dump({'chars': chars, 'matrix': matrix, 'report': report},
                  f, ensure_ascii=False, indent=1)
    print('\n报告:', out)


if __name__ == '__main__':
    main()
