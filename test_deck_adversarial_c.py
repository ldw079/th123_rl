# -*- coding: utf-8 -*-
"""C(用户2026-10-07"只做DCB"): 对抗性卡组池行为测试。"""
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from deck_sampler import (sample_deck_weighted,  # noqa: E402
                          sample_archetype_deck, archetype_of,
                          ARCHETYPES)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    rng = random.Random(42)

    # 1. 无统计=均匀(中性)
    cnt = collections.Counter(
        sample_deck_weighted(0, rng)[1] for _ in range(4000))
    mx = max(cnt.values()) / 4000
    check('无统计近均匀', 0.15 < mx < 0.35,
          str(dict(cnt)))

    # 2. 弱流派被加权: 对sc流 0W-20L → 权重1.0 vs 中性0.5×3
    #    → 期望占比≈40%(2×均匀) — 显著但不淹没(单流派过采会饿死其他)
    stats = {'sc': [0, 20]}
    cnt = collections.Counter(
        sample_deck_weighted(0, rng, stats)[1] for _ in range(4000))
    sc_share = cnt['sc'] / 4000
    check('弱流派加权(≈2×均匀)', 0.33 < sc_share < 0.47
          and cnt['sc'] == max(cnt.values()),
          'sc占%.0f%% %s' % (sc_share * 100, dict(cnt)))

    # 3. 强势流派降权: skill 20W-0L → 占比应低于均匀
    stats = {'skill': [20, 0]}
    cnt = collections.Counter(
        sample_deck_weighted(0, rng, stats)[1] for _ in range(4000))
    sk_share = cnt['skill'] / 4000
    check('强流派降权', sk_share < 0.25, 'skill占%.0f%%' % (sk_share * 100))

    # 4. 样本<3局=中性(不被单局噪声带偏)
    stats = {'sc': [0, 2]}
    cnt = collections.Counter(
        sample_deck_weighted(0, rng, stats)[1] for _ in range(4000))
    mx = max(cnt.values()) / 4000
    check('小样本中性', 0.15 < mx < 0.35, 'max=%.0f%%' % (mx * 100))

    # 5. 加权产物往返: 抽到的archetype与分类一致
    ok = True
    for _ in range(200):
        d, a = sample_deck_weighted(0, rng)
        if a != 'mixed' and archetype_of(d) != a:
            ok = False
    check('加权往返一致', ok)

    # 6. 合法性: 20张/每卡≤4
    ok = True
    for eng in (0, 1, 9):
        for a in ARCHETYPES:
            d = sample_archetype_deck(eng, rng, a)
            if len(d) != 20 or max(
                    collections.Counter(d).values()) > 4:
                ok = False
    check('合法卡组', ok)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
