# -*- coding: utf-8 -*-
"""D(用户2026-10-07"只做DCB"): 流派 matchup 仪表 — 同角色镜像,
对手卡组固定为三类原型, 我方正常课程采样 → 分流派胜率表。

回答: "同一角色的不同卡组流派, 我方模型胜率掉不掉、掉多少" —
此前所有评估(F6/E1)全用系统卡组, 此维度从未被测量。

用法: python tools/deck_matchup.py [--chars reimu,marisa,suika]
                                 [--games 3] [--port 20912]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

from side_driver import SideDriver, EvalEnv  # noqa: E402
from tm_env import CHAR  # noqa: E402
from deck_sampler import (sample_deck, sample_archetype_deck,  # noqa: E402
                          archetype_of)
from train_tm import CHAR_LIBS  # noqa: E402

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
FRAME_CAP = 45000


def run_game(char, port, my_deck, opp_deck):
    """一局镜像: 我方(左)正常模型 vs 同模型对手(右), 双方卡组指定。
    返回 'win'/'lose'/'draw'。胜局判定: GameEnded→last_match;
    帧上限→回合比分→HP差(与F6同款口径)。"""
    da = SideDriver(char, 'L')
    db = SideDriver(char, 'R')
    da.load(os.path.join(STORE, 'model_ppo_%s.npz' % char))
    db.load(os.path.join(STORE, 'model_ppo_%s.npz' % char))
    env = EvalEnv(port, char_left=char, char_right=char, vs_com=False,
                  tps=480, deck_left=my_deck, deck_right=opp_deck)
    ia = ib = {}
    sl = sr = 0
    lh = rh = 10000
    result = 'draw'
    try:
        for f in range(FRAME_CAP):
            r = env.step(ia, ib)
            if env.last_match:
                _w, ls, rs = env.last_match
                result = 'win' if ls > rs else 'lose'
                env.last_match = None
                break
            if r is None:
                break
            left, right, weather, objs = r
            sl, sr = left.get('score', 0), right.get('score', 0)
            lh, rh = left.get('hp', 0), right.get('hp', 0)
            if f < 60:
                continue
            ia = da.frame_input(left, right, weather, objs, []) or {}
            ib = db.frame_input(right, left, weather, objs, []) or {}
        else:
            if sl != sr:
                result = 'win' if sl > sr else 'lose'
                print('    [顶时判定 比分%d-%d]' % (sl, sr))
            elif lh != rh:
                result = 'win' if lh > rh else 'lose'
                print('    [顶时判定 HP差]')
    except Exception as e:
        print('    [异常 %s: %s — 不计]' % (type(e).__name__, e))
        result = 'draw'
    finally:
        try:
            env.close()
        except Exception:
            pass
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--games', type=int, default=3)
    ap.add_argument('--port', type=int, default=20912)
    args = ap.parse_args()
    chars = args.chars.split(',')

    rng = random.Random(20261007)
    report = {}
    for char in chars:
        eng = CHAR[char]
        report[char] = {}
        for arch in ('system', 'skill', 'sc'):
            w = l = d = 0
            for g in range(args.games):
                my = sample_deck(eng, rng, 0.7)      # 我方=生产条件
                opp = sample_archetype_deck(eng, rng, arch)
                print('[%s vs %s流] 第%d局(我方%s/对手%s)...'
                      % (char, arch, g + 1, archetype_of(my),
                         archetype_of(opp)))
                r = run_game(char, args.port, my, opp)
                if r == 'win':
                    w += 1
                elif r == 'lose':
                    l += 1
                else:
                    d += 1
            n = w + l
            wr = w / n if n else None
            report[char][arch] = {'win': w, 'lose': l, 'draw': d,
                                  'wr': wr}
            print('  %s vs %s流: %dW-%dL-%dD = %s'
                  % (char, arch, w, l, d,
                     '%.0f%%' % (wr * 100) if wr is not None else '无有效局'))

    print('\n===== 流派 matchup 总表(我方胜率) =====')
    print('%-8s %8s %8s %8s' % ('角色', '系统流', '技能流', 'SC流'))
    for char in chars:
        row = []
        for arch in ('system', 'skill', 'sc'):
            wr = report[char][arch]['wr']
            row.append('%7s' % ('%.0f%%' % (wr * 100)
                                if wr is not None else '—'))
        print('%-8s %s' % (char, ' '.join(row)))

    out = os.path.join(
        HERE, 'deck_matchup_%s.json' % time.strftime('%Y%m%d'))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('\n报告:', out)


if __name__ == '__main__':
    main()
