# -*- coding: utf-8 -*-
"""R61s(F6)行为测试: 380 matchup评估体系(分析层, 不跑游戏).

R63(F6)重写要点: 原测试第5项断言 `sd['metric'] > 0.5`, 而该 metric 是
`avg_wr - var` 的占位口径 —— 断言"通过"只是因为它恰好>0.5, 不是因为它
有意义。本测试改为钉**新口径的定义**:
  1. Wilson 区间对极端比例(0/3, 3/3)不越界、不宽0;
  2. 最差对位下界**只会被真实弱对位拉低**(强对位不能救场) — 这是"无弱
     对位"这一超人特征的可证伪代理;
  3. 样本不足的对位**不参与**判定且被列出(而不是当0或忽略);
  4. 人类锚来自真实重放数据且带区间;
  5. 同口径才给"距离"(人-人 vs 模型-模型 → comparable=False), 不硬造数字。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from tools.eval_matrix import analyze, available_chars, has_model
from tools.superhuman_gauge import (wilson, wilson_lower, rate,
                                    gauge_from_matrix, load_human_baseline,
                                    matchup_rates)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    # 1. 三现役可用
    chars = available_chars(3)
    check('三现役', chars == ['reimu', 'marisa', 'suika'])

    # 2. 模型存在检测
    check('reimu有模型', has_model('reimu'))
    check('不存在角色无模型', not has_model('nonexistent'))

    # ---- 3. Wilson 统计基础 ----
    lo, hi = wilson(3, 3)
    check('3/3区间合法', 0.0 <= lo <= hi <= 1.0 and lo < hi and lo < 1.0,
          '[%.3f,%.3f]' % (lo, hi))
    lo0, hi0 = wilson(0, 3)
    check('0/3区间合法', lo0 == 0.0 and 0.0 < hi0 < 1.0,
          '[%.3f,%.3f]' % (lo0, hi0))
    check('n=0 → 全区间(不冒充0)', wilson(0, 0) == (0.0, 1.0))
    check('样本越大下界越高',
          wilson_lower(5, 10) < wilson_lower(500, 1000),
          '%.4f < %.4f' % (wilson_lower(5, 10), wilson_lower(500, 1000)))
    check('rate(0,0).wr is None', rate(0, 0)['wr'] is None)

    # ---- 4. 分析器: 合成矩阵(旧接口兼容) ----
    matrix = {
        'reimu|marisa': {'a_wins': 3, 'b_wins': 1, 'games': 4},
        'reimu|suika': {'a_wins': 1, 'b_wins': 3, 'games': 4},
        'marisa|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4},
    }
    report = analyze(matrix, ['reimu', 'marisa', 'suika'])
    check('排名非空', len(report['ranking']) == 3)
    check('有超人距离键(向后兼容)', 'superhuman_distance' in report)
    check('metric改名为可证伪口径',
          report['superhuman_distance']['metric_name']
          == 'worst_matchup_wilson_lower')
    check('小样本(4局/对位)可参与判定', report['dominance']['worst_lower']
          is not None,
          'worst_lower=%.3f' % (report['dominance']['worst_lower'] or -1))
    check('人-人vs模型-模型 → 不可相减',
          report['comparison']['comparable'] is False
          and report['comparison']['distance'] is None)
    check('给出不可相减的原因', '对手' in report['comparison']['reason'])

    # ---- 5. 平衡矩阵(各50%) ----
    matrix_bal = {
        'reimu|marisa': {'a_wins': 2, 'b_wins': 2, 'games': 4},
        'reimu|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4},
        'marisa|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4},
    }
    report_bal = analyze(matrix_bal, ['reimu', 'marisa', 'suika'])
    wrs = {r['char']: r['avg_wr'] for r in report_bal['ranking']}
    check('平衡各50%', all(abs(w - 0.5) < 0.01 for w in wrs.values()),
          str(wrs))

    # ---- 6. 核心语义: 最差对位下界只被弱对位拉低 ----
    # a 对 b/c/d 全胜(3/3), 但被 e 打 0/4 → 下界必须≈0(强对位救不了场)
    m_weak = {
        'a|b': {'a_wins': 3, 'b_wins': 0, 'games': 3},
        'a|c': {'a_wins': 3, 'b_wins': 0, 'games': 3},
        'a|d': {'a_wins': 3, 'b_wins': 0, 'games': 3},
        'a|e': {'a_wins': 0, 'b_wins': 4, 'games': 4},
    }
    r_weak = gauge_from_matrix(m_weak, ['a', 'b', 'c', 'd', 'e'],
                               min_games=3)
    a_row = [r for r in r_weak['ranking'] if r['char'] == 'a'][0]
    check('弱对位锁定最差', a_row['worst_opp'] == 'e',
          'worst_opp=%s' % a_row['worst_opp'])
    check('最差对位下界≈0(不被全胜平均掉)',
          a_row['worst_lower'] < 0.15,
          'worst_lower=%.3f' % a_row['worst_lower'])
    check('平均胜率仍高(证明"平均值会骗人")',
          a_row['avg_wr'] > 0.65, 'avg_wr=%.3f (9W/13局)' % a_row['avg_wr'])
    check('全局dominance取最弱', r_weak['dominance']['worst_char'] == 'a'
          and r_weak['dominance']['worst_opp'] == 'e')

    # ---- 7. 小样本对位不参与判定但被列出 ----
    m_small = {
        'a|b': {'a_wins': 3, 'b_wins': 0, 'games': 3},
        'a|c': {'a_wins': 1, 'b_wins': 0, 'games': 1},   # 1局: 不足
    }
    r_small = gauge_from_matrix(m_small, ['a', 'b', 'c'], min_games=3)
    a_s = [r for r in r_small['ranking'] if r['char'] == 'a'][0]
    check('1局对位被排除出判定', a_s['worst_opp'] == 'b'
          and a_s['n_pairs_eligible'] == 1,
          'worst=%s eligible=%d %s' % (a_s['worst_opp'],
                                       a_s['n_pairs_eligible'],
                                       a_s['pairs'].keys()))
    check('1局对位仍被报告(不隐藏)', 'c' in a_s['pairs']
          and a_s['pairs']['c']['games'] == 1)
    check('样本不足 → 不伪造数值',
          gauge_from_matrix({}, ['x'], min_games=3)['dominance']
          ['worst_lower'] is None)

    # ---- 8. 双边口径: 两侧都拿到对位(修 marisa 恒在 b 侧的空手洞) ----
    _m1 = {'a|b': {'a_wins': 2, 'b_wins': 0, 'games': 2}}
    per = matchup_rates(_m1, ['a', 'b'])
    check('双边: a视角有对位', per['a']['pairs'].get('b', {}).get('wins') == 2)
    check('双边: b视角同样有对位(互补)',
          per['b']['pairs'].get('a', {}).get('wins') == 0
          and per['b']['pairs']['a']['wr'] == 0.0,
          str(per['b']['pairs'].get('a')))
    check('双边: 完全无对位的角色 → insufficient(缺失而非0)',
          'b' in matchup_rates({}, ['a', 'b'])['a']['insufficient'])
    per_b = matchup_rates(_m1, ['a', 'b'], our_side='b')
    check('our_side=b 只取b视角', 'a' in per_b['b']['pairs']
          and not per_b['a']['pairs'])
    # 回归: 恒在 b 侧的角色不得再出现 avg_wr=None(旧口径的覆盖洞)
    _m2 = {'reimu|marisa': {'a_wins': 2, 'b_wins': 2, 'games': 4},
           'marisa|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4}}
    per2 = matchup_rates(_m2, ['reimu', 'marisa', 'suika'])
    check('恒为b侧角色仍有完整均率(覆盖洞回归)',
          per2['marisa']['agg']['wr'] == 0.5
          and len(per2['marisa']['pairs']) == 2,
          'marisa avg=%s pairs=%s' % (per2['marisa']['agg']['wr'],
                                      sorted(per2['marisa']['pairs'])))

    # ---- 9. 人类锚: 真实重放数据 ----
    hb = load_human_baseline()
    check('人类锚有真实局数', hb['n_matches'] >= 100,
          'n=%d / %d shard' % (hb['n_matches'], hb['sources']))
    check('逐角色带区间',
          all(r['lo'] <= r['wr'] <= r['hi'] for r in hb['chars'].values()))
    check('逐对位存在', len(hb['matchups']) >= 3,
          '%d对位' % len(hb['matchups']))
    check('锚自带口径警告', '不可相减' in hb['caveat'])
    check('标注还缺同口径锚(真人vs COM)',
          'COM' in hb['missing_for_ideal_gauge'])

    # ---- 11. COM 标尺: 真人实测打COM=100% → 天花板饱和 ----
    # 用户实测(2026-10-07): "真人对COM胜率百分之百, COM远逊于真人"。
    # 这条事实决定了 COM **不能**当超人距离的分母: 人类与超人在该标尺上同为100%。
    from tools.superhuman_gauge import (COM_VS_HUMAN, com_ruler_verdict,
                                        gauge_from_matrix as _g)
    check('COM人类基线记录在案(用户实测)', COM_VS_HUMAN['human_wr'] == 1.0)
    check('COM标尺标注为天花板饱和',
          COM_VS_HUMAN['discriminates_at_top'] is False)
    v_bad = com_ruler_verdict(0.3, n_games=10)
    check('对COM输 → 确定低于人类下限', v_bad['verdict'] == 'below_human_floor',
          str(v_bad.get('model_ci')))
    v_small = com_ruler_verdict(1.0, n_games=40)
    check('全胜但样本小 → 与人类不可区分(不吹超人)',
          v_small['verdict'] == 'indistinguishable_from_human',
          str(v_small.get('model_ci')))
    v_big = com_ruler_verdict(1.0, n_games=500)
    check('大样本全胜 → "未观测到低于人类"但仍拒绝称超人',
          v_big['verdict'] == 'at_or_above_human_on_saturated_ruler'
          and any('超人' in s for s in v_big['cannot_conclude']),
          str(v_big.get('model_ci')))
    check('无数据不判定', com_ruler_verdict(None, n_games=0)['verdict']
          == 'no_data')
    _rep = _g({'a|b': {'a_wins': 2, 'b_wins': 0, 'games': 2}}, ['a', 'b'])
    check('报告带com_ruler能/不能', 'com_ruler' in _rep
          and '超人' in _rep['com_ruler']['cannot_do']
          and '下限' in _rep['com_ruler']['can_do'])
    check('报告caveat点名COM饱和',
          any('饱和' in c for c in _rep['caveat']))

    # ---- 12. 空矩阵不崩 ----
    report3 = analyze({}, ['x'])
    check('空矩阵安全', 'ranking' in report3)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
