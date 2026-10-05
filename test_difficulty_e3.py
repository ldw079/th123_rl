# -*- coding: utf-8 -*-
"""R61q(E3)行为测试: 校准难度对局系统."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from difficulty import (DifficultyController, DIFFICULTY_PRESETS,
                        difficulty_ladder, calibrate)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    # 1. 预设完整性
    check('四档预设', set(DIFFICULTY_PRESETS) ==
          {'easy', 'normal', 'hard', 'full'})

    # 2. 温度调整方向
    for level, expect_higher in [('easy', True), ('hard', False),
                                 ('full', False)]:
        ctrl = DifficultyController(level)
        t = ctrl.temperature(1.5)
        if expect_higher:
            check('%s温度升高' % level, t > 1.5, '%.1f' % t)
        else:
            check('%s温度≤模型' % level, t <= 1.5 + 0.01, '%.1f' % t)

    # 3. 掩码限制
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS['reimu']
    base = np.ones(len(lib['macros']), dtype=bool)
    easy = DifficultyController('easy')
    m_easy = easy.apply_mask(base, lib)
    sc_macros = [n for n in lib['sc'] if n in lib['names']]
    sc_idx = [lib['names'].index(n) for n in sc_macros]
    check('easy禁SC', all(not m_easy[i] for i in sc_idx),
          '禁%d个SC宏' % len(sc_idx))
    skill_macros = [n for n in lib['skill'] if n in lib['names']]
    skill_idx = [lib['names'].index(n) for n in skill_macros]
    check('easy禁技能', all(not m_easy[i] for i in skill_idx))
    check('easy非全禁', m_easy.any())

    # 4. hard全开
    hard = DifficultyController('hard')
    m_hard = hard.apply_mask(base, lib)
    check('hard全开', (m_hard == base).all())

    # 5. 牌组模式
    import random
    rng = random.Random(0)
    deck_sys = easy.sample_deck(0, rng)
    check('easy纯系统卡', all(cid < 100 for cid in deck_sys))

    # 6. 难度阶梯
    ladder = difficulty_ladder(3)
    check('阶梯三档', [s['level'] for s in ladder] ==
          ['easy', 'normal', 'hard'])
    check('阶梯各3局', all(s['games'] == 3 for s in ladder))

    # 7. 校准推荐
    hist_win = [{'level': 'easy', 'win': True}] * 8
    level, reason = calibrate(hist_win)
    check('高胜率升级', level == 'normal', '%s(%s)' % (level, reason))
    hist_lose = [{'level': 'hard', 'win': False}] * 8
    level2, reason2 = calibrate(hist_lose)
    check('低胜率降级', level2 == 'normal', '%s(%s)' % (level2, reason2))
    hist_mixed = [{'level': 'normal', 'win': True},
                  {'level': 'normal', 'win': False}] * 4
    level3, _ = calibrate(hist_mixed)
    check('五五开维持', level3 == 'normal')

    # 8. 无效难度
    try:
        DifficultyController('impossible')
        check('无效难度报错', False)
    except ValueError:
        check('无效难度报错', True)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
