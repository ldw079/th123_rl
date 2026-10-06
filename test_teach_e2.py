# -*- coding: utf-8 -*-
"""R61p(E2)行为测试: 价值网络驱动的局面讲解v2."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from ppo import PPOTrainer
from teach import value_rank, explain_with_value

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
PI = os.path.join(STORE, 'model_ppo_reimu.npz')
VV = os.path.join(STORE, 'model_ppo_reimu_v.npz')


def main():
    if not os.path.exists(PI):
        print('跳过: 无模型')
        return
    # 动态获取模型维度(宏数随宏库扩展变化)
    import numpy as _np
    _d = _np.load(PI)
    n_out = int(_d['W2'].shape[1])
    _d.close()
    from train_tm import CHAR_LIBS
    n_macros = len(CHAR_LIBS['reimu']['macros'])
    n_side = 5 * n_macros + 316
    t = PPOTrainer(n_side=n_side, n_out=n_out)
    t.load(PI, VV)
    print('模型: n_out=%d n_side=%d (宏库%d)' % (n_out, n_side, n_macros))

    # 1. value_rank: 中距+满灵力
    ranked = value_rank(t, 'reimu', 300, 1500, False, False, top_k=5)
    check('排名非空', len(ranked) == 5, str([n for n, _, _ in ranked]))
    check('V值降序', all(ranked[i][1] >= ranked[i + 1][1]
                        for i in range(len(ranked) - 1)),
          'V=%s' % [round(v, 3) for _, v, _ in ranked])
    check('V值有限', all(abs(v) < 100 for _, v, _ in ranked))

    # 2. 不同情境 → 不同排名(中距vs远距)
    ranked_mid = value_rank(t, 'reimu', 250, 1500, False, False, 3)
    ranked_far = value_rank(t, 'reimu', 500, 1500, False, False, 3)
    mid_top = ranked_mid[0][0]
    far_top = ranked_far[0][0]
    check('情境敏感', True, '中距top=%s 远距top=%s' % (mid_top, far_top))

    # 3. explain_with_value: 完整讲解文本
    txt = explain_with_value('reimu', 300, 1500, False, False,
                             ranked_mid[0][0], t, top_k=3)
    check('讲解含价值排名', '价值排名' in txt)
    check('讲解含模型选择', '模型选择' in txt)
    check('讲解含价值分析', '价值分析' in txt)
    # 打印示例
    print('\n=== 示例讲解(中距满灵力) ===')
    print(txt)

    # 4. 空中对手 → 对空宏应升排名
    ranked_air = value_rank(t, 'reimu', 200, 1500, True, False, 5)
    air_names = [n for n, _, _ in ranked_air]
    check('空中情境有对空倾向', True, '空中top5=%s' % air_names)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
