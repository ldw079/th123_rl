# -*- coding: utf-8 -*-
"""R61s(F6)行为测试: 380 matchup评估体系(分析层, 不跑游戏)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from tools.eval_matrix import analyze, available_chars, has_model

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

    # 3. 分析器: 合成矩阵
    matrix = {
        'reimu|marisa': {'a_wins': 3, 'b_wins': 1, 'games': 4},
        'reimu|suika': {'a_wins': 1, 'b_wins': 3, 'games': 4},
        'marisa|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4},
    }
    report = analyze(matrix, ['reimu', 'marisa', 'suika'])
    check('排名非空', len(report['ranking']) == 3)
    check('有超人距离', 'superhuman_distance' in report)

    # 4. 平衡矩阵(各50%)
    matrix_bal = {
        'reimu|marisa': {'a_wins': 2, 'b_wins': 2, 'games': 4},
        'reimu|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4},
        'marisa|suika': {'a_wins': 2, 'b_wins': 2, 'games': 4},
    }
    report_bal = analyze(matrix_bal, ['reimu', 'marisa', 'suika'])
    wrs = {r['char']: r['avg_wr'] for r in report_bal['ranking']}
    check('平衡各50%', all(abs(w - 0.5) < 0.01 for w in wrs.values()),
          str(wrs))

    # 5. 强弱分明
    matrix2 = {
        'a|b': {'a_wins': 4, 'b_wins': 0, 'games': 4},
        'a|c': {'a_wins': 3, 'b_wins': 1, 'games': 4},
        'b|c': {'a_wins': 1, 'b_wins': 3, 'games': 4},
    }
    report2 = analyze(matrix2, ['a', 'b', 'c'])
    top = report2['ranking'][0]
    check('a排第一', top['char'] == 'a' and top['avg_wr'] > 0.8)
    sd = report2['superhuman_distance']
    check('超人指标>0.5', sd['metric'] > 0.5, '%.3f' % sd['metric'])

    # 6. 空矩阵不崩
    report3 = analyze({}, ['x'])
    check('空矩阵安全', 'ranking' in report3)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
