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
                          archetype_of, sample_skillset_deck)
from train_tm import CHAR_LIBS  # noqa: E402
from card_tables import CHAR_CARD_TABLES  # noqa: E402

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


def skillset_groups(eng):
    """L2(用户2026-10-07): 必杀系别对照组 — 每角色三组固定技能装备
    (前段系/后段系/混合系), 名字从card_tables取(人类可读)。"""
    cards = CHAR_CARD_TABLES[eng]
    names = {int(i): n for i, n, c in cards if 100 <= int(i) < 200}
    ids = sorted(names)
    if not ids:
        return []
    third = max(4, len(ids) // 3)
    return [
        ('前段系', ids[:third], names),
        ('后段系', ids[-third:], names),
        ('混编系', ids[::2][:third] if len(ids) > third else ids, names),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--games', type=int, default=3)
    ap.add_argument('--port', type=int, default=20912)
    ap.add_argument('--mode', default='arch',
                    choices=['arch', 'skillset'],
                    help='arch=L1流派比例 | skillset=L2必杀系别')
    args = ap.parse_args()
    chars = args.chars.split(',')

    rng = random.Random(20261007)
    report = {}
    for char in chars:
        eng = CHAR[char]
        report[char] = {}
        # 对照组: arch=每局在原型内重抽(比例层随机性);
        # skillset=固定装备的系别卡组(身份层, 局间不变)
        if args.mode == 'arch':
            variants = list(('system', 'skill', 'sc'))
            fixed = {}
        else:
            fixed = {}
            for gname, sids, _names in skillset_groups(eng):
                fixed[gname] = sample_skillset_deck(eng, sids, rng)
            variants = list(fixed.keys())
        for vname in variants:
            w = l = d = 0
            for g in range(args.games):
                my = sample_deck(eng, rng, 0.7)      # 我方=生产条件
                if args.mode == 'arch':
                    opp = sample_archetype_deck(eng, rng, vname)
                else:
                    opp = fixed[vname]
                print('[%s vs %s] 第%d局(我方%s)...'
                      % (char, vname, g + 1, archetype_of(my)))
                r = run_game(char, args.port, my, opp)
                if r == 'win':
                    w += 1
                elif r == 'lose':
                    l += 1
                else:
                    d += 1
            n = w + l
            wr = w / n if n else None
            report[char][vname] = {'win': w, 'lose': l, 'draw': d,
                                   'wr': wr}
            print('  %s vs %s: %dW-%dL-%dD = %s'
                  % (char, vname, w, l, d,
                     '%.0f%%' % (wr * 100) if wr is not None else '无有效局'))

    print('\n===== %s matchup 总表(我方胜率) ====='
          % ('流派' if args.mode == 'arch' else '必杀系别'))
    cols = list(next(iter(report.values())).keys()) if report else []
    print('%-8s %s' % ('角色',
                       ' '.join('%8s' % c for c in cols)))
    for char in chars:
        row = []
        for v in cols:
            wr = report[char].get(v, {}).get('wr')
            row.append('%7s' % ('%.0f%%' % (wr * 100)
                                if wr is not None else '—'))
        print('%-8s %s' % (char, ' '.join(row)))

    if args.mode == 'skillset':
        print('\n(系别构成)')
        for char in chars:
            eng = CHAR[char]
            for gname, sids, names in skillset_groups(eng):
                print('  %s %s: %s' % (char, gname,
                                       ' '.join(names[s] for s in sids)))

    out = os.path.join(
        HERE, 'deck_matchup_%s_%s.json'
        % (args.mode, time.strftime('%Y%m%d')))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('\n报告:', out)


if __name__ == '__main__':
    main()
