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
    timeout_n = 0        # A1-1: 顶时局数(被动性仪表的评估侧)
    timeout_loss = 0     # 顶时判负(a侧视角)
    hp_diffs = []        # 顶时HP差
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
                    # P2(审计#3): 原平局记右方胜 — 三态修正
                    if ls > rs:
                        a_wins += 1
                    elif rs > ls:
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
                timeout_n += 1
                if _sl != _sr:
                    if _sl > _sr:
                        a_wins += 1
                    else:
                        b_wins += 1
                        timeout_loss += 1
                    print('  [eval] 顶时判定: 回合比分%d-%d' % (_sl, _sr))
                elif left.get("hp", 0) != right.get("hp", 0):
                    hp_diffs.append(left["hp"] - right["hp"])
                    if left["hp"] > right["hp"]:
                        a_wins += 1
                    else:
                        b_wins += 1
                        timeout_loss += 1
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

    return {'a_wins': a_wins, 'b_wins': b_wins, 'games': games,
            'timeout_n': timeout_n, 'timeout_loss': timeout_loss,
            'timeout_hp_mean': (sum(hp_diffs) / len(hp_diffs)
                                if hp_diffs else None)}


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


def four_lenses(matrix, chars, sup_log=None):
    """W3(研究借鉴方案§3): 四口径并列输出 — 针对价值/种群平均/最坏反制
    剩余/适应后持续(笔记§五·深入七)。零新测量: 前两口径来自本矩阵,
    后两口径读league日志(exploit衰减/固化指数)。并列不合成总分。"""
    import os
    lens = {'targeted_value': None, 'population_avg': None,
            'worst_exploit': None, 'adapt_persistence': None,
            'notes': []}
    rows = [v for v in matrix.values() if isinstance(v, dict)
            and 'games' in v]
    if rows:
        wrs = []
        worst = None
        for k, v in matrix.items():
            if not isinstance(v, dict) or 'games' not in v or v['games'] < 1:
                continue
            w = v.get('wins', v.get('a_wins', 0))
            wr = w / v['games']
            wrs.append(wr)
            if worst is None or wr < worst[1]:
                worst = (k, wr, v['games'])
        if wrs:
            lens['population_avg'] = round(sum(wrs) / len(wrs), 3)
        if worst:
            lens['targeted_value'] = {
                'pair': worst[0], 'wr': round(worst[1], 3),
                'games': worst[2]}
    sup_log = sup_log or r'D:	emp	h123_modelsleet_supervision.log'
    try:
        from tools.league_weekly import parse_league_blocks, analyze             as lw_analyze
        blocks = parse_league_blocks(sup_log)
        rep = lw_analyze(blocks)
        if rep:
            lens['adapt_persistence'] = rep.get('consolidation_index')
            ed = rep.get('exploit_decay') or {}
            if ed:
                wl = min(ed.items(), key=lambda kv: kv[1]['main_wr_last'])
                lens['worst_exploit'] = {
                    'label': wl[0],
                    'main_wr': wl[1]['main_wr_last'],
                    'games': wl[1]['games'],
                    'verdict': wl[1]['verdict']}
            else:
                lens['notes'].append('league日志无exploit条目')
    except Exception as e:
        lens['notes'].append('league读数不可用(%s)' % str(e)[:60])
    return lens


def analyze(matrix, chars):
    """分析矩阵 → 排名/克星/超人距离(对抗池广度 + 人类锚)。

    R63(F6)重写: 原 `metric = top['avg_wr'] - top['var']` 是**占位口径**
    (用一个胜率的"均值"减"方差", 无统计意义; 且不含任何基准 → 不是"距离")。
    现委托 `tools/superhuman_gauge.py`:
      - `dominance`: 最薄弱对位的 Wilson 95% 下界(样本不足的对位不参与)
      - `human_anchor`: 真实人类重放基线(191局, 带区间) — 项目唯一真人数据
      - `comparison`: 只在**同口径**时给"距离"; 否则给出不可相减的原因
    `report['superhuman_distance']` 旧键保留(向后兼容/门禁锚点), 但内容改为
    带区间与样本量的结构, 不再冒充"距离"。
    """
    from tools.superhuman_gauge import gauge_from_matrix
    g = gauge_from_matrix(matrix, chars)
    report = {
        'ranking': g['ranking'],
        'matrix_size': len(matrix),
        'dominance': g['dominance'],
        'human_anchor': g['human_anchor'],
        'comparison': g['comparison'],
        'caveat': g['caveat'],
    }
    d = g['dominance']
    # A1-1: 被动性汇总(评估侧) — 顶时率/顶时判负率/顶时HP差
    tn = sum(v.get('timeout_n', 0) for v in matrix.values())
    tg = sum(v.get('games', 0) for v in matrix.values())
    tl = sum(v.get('timeout_loss', 0) for v in matrix.values())
    hps = [v['timeout_hp_mean'] for v in matrix.values()
           if v.get('timeout_hp_mean') is not None]
    # W3: 四口径并列(报告层新增, 不动既有键)
    try:
        report['four_lenses'] = four_lenses(matrix, chars)
    except Exception as e:
        report['four_lenses'] = {'notes': ['四口径构建失败(%s)' % e]}
    report['passivity'] = {
        'timeout_rate': (tn / tg if tg else None),
        'timeout_loss_share': (tl / tn if tn else None),
        'timeout_hp_mean_avg': (sum(hps) / len(hps) if hps else None),
    }
    report['superhuman_distance'] = {
        'metric': d['worst_lower'],          # None = 样本不足(不再伪造数值)
        'metric_name': 'worst_matchup_wilson_lower',
        'worst_char': d['worst_char'],
        'worst_opp': d['worst_opp'],
        'eligible_pairs': d['eligible_pairs'],
        'comparable_to_human': g['comparison']['comparable'],
        'note': ('最薄弱对位的Wilson下界(越高=越无弱对位)。'
                 '**不是**与人类/满分的距离 — 见comparison. '
                 '同架构互打只度量对抗池广度, 非角色强度。'
                 if d['worst_lower'] is not None else
                 '样本不足(min_games=%d) — 无数值(不伪造)' % g['min_games']),
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

    # W3: 四口径并列打印(不合成总分)
    fl = report.get('four_lenses')
    if fl:
        print('\n=== 四口径(W3, 并列不合成) ===')
        tv = fl.get('targeted_value')
        print('  针对价值(最弱对位): %s'
              % ('%s %.0f%%(%d局)' % (tv['pair'], tv['wr'] * 100,
                                      tv['games']) if tv else '-'))
        print('  种群平均(对位均值): %s'
              % ('%.0f%%' % (fl['population_avg'] * 100)
                 if fl.get('population_avg') is not None else '-'))
        we = fl.get('worst_exploit')
        print('  最坏反制剩余(exploit): %s'
              % ('%s 主胜率%.0f%%(%d局) %s'
                 % (we['label'], we['main_wr'] * 100, we['games'],
                    we['verdict']) if we else '-'))
        print('  适应后持续(固化指数): %s'
              % (fl.get('adapt_persistence')
                 if fl.get('adapt_persistence') is not None else '-'))
        for nt in fl.get('notes', []):
            print('    注: %s' % nt)
    print('\n=== 排名(按平均对位胜率; 非角色强度) ===')
    for i, r in enumerate(report['ranking'], 1):
        wr = r['avg_wr']
        print('%2d. %-10s 平均对位胜率%s 对位%d(可用%d) 最弱%s=%s (%d局)'
              % (i, r['char'],
                 ('  n/a ' if wr is None else '%5.1f%%' % (wr * 100)),
                 r['n_pairs'], r['n_pairs_eligible'],
                 r['worst_opp'] or '-',
                 ('n/a' if r['worst_lower'] is None
                  else '%.3f' % r['worst_lower']), r['games']))
    try:
        from tools.superhuman_gauge import format_report
        print()
        print(format_report({'dominance': report['dominance'],
                             'ranking': report['ranking'],
                             'human_anchor': report['human_anchor'],
                             'comparison': report['comparison'],
                             'our_side': 'bilateral', 'min_games': 4},
                            top=len(report['ranking'])))
    except Exception as e:
        sd = report.get('superhuman_distance', {})
        print('\n=== 超人距离(退化打印) ===')
        print('  %s' % sd.get('note'))
        print('  (%s)' % e)

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
