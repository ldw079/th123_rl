# -*- coding: utf-8 -*-
"""BH-3.2行为测试(行为健康方案v4): 守备段位逐角色精确表 —
旧全局表两条实测错误(2B/2C蹲防必虚报+3A一律中段漏报)的修正钉死。"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from feat_builder import (FeatureBuilder, LOW_ATTACK_IDS,
                          LOW_ATTACK_IDS_BY_CHAR)

PASS, FAIL = [], []
W = {'id': 0, 'active': 0, 'displayed': None}
BASE = {'spirit': 1000, 'position.y': 50.0, 'hp': 10000, 'action': 0,
        'cardGauge': 0, 'score': 0, 'hand': b'\xff' * 10,
        'comboDamage': 0, 'untech': 0, 'airBorne': False, 'timeStop': 0,
        'hitStop': 0, 'guardCount': 0}
LOW_BIT = 303   # 段14i下段位(差分定位; 与动作ID 303数值同纯属巧合)


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def low_bit(opp_name, opp_action):
    fb = FeatureBuilder(88)
    if opp_name is not None:
        fb._opp_char = opp_name
    l = dict(BASE)
    l['position.x'] = 500.0
    l['direction'] = 1
    r = dict(BASE)
    r['position.x'] = 700.0
    r['action'] = opp_action
    return float(np.asarray(fb.build(l, r, W, []))[LOW_BIT])


def main():
    # ===== 数据表完整性 =====
    gt = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'data', 'guide_tables',
        'guard_height.json')
    check('表档存在', os.path.exists(gt))
    d = json.load(io.open(gt, encoding='utf-8'))
    check('20角色全覆盖', len(d['low']) == 20, str(len(d['low'])))
    check('出处可审计', 'cleista' in d['source'])
    check('逐招明细在案', len(d.get('per_move', {})) >= 20)

    # ===== 旧表错误修正①: 2B/2C蹲防必=虚报(实测全20角色无blockLow) =====
    for ch in ('reimu', 'marisa', 'suika'):
        check('%s 2B(402)不触发(旧虚报修正)' % ch,
              low_bit(ch, 402) == 0.0)
        check('%s 2C(412)不触发(旧虚报修正)' % ch,
              low_bit(ch, 412) == 0.0)

    # ===== 旧表错误修正②: 3A段位角色分化 =====
    check('suika 3A(304)触发(旧漏报修正)', low_bit('suika', 304) == 1.0)
    check('marisa 3A触发', low_bit('marisa', 304) == 1.0)
    check('reimu 3A不触发(blockHigh实测)', low_bit('reimu', 304) == 0.0)
    check('komachi 3A不触发', low_bit('komachi', 304) == 0.0)
    check('remilia 3A触发(唯2A非下段角色)', low_bit('remilia', 304) == 1.0)

    # ===== 基础下段仍触发 =====
    check('reimu 2A(303)触发', low_bit('reimu', 303) == 1.0)
    check('suika f2A(311)触发', low_bit('suika', 311) == 1.0)
    check('reimu 66B(408)触发', low_bit('reimu', 408) == 1.0)

    # ===== j2A按角色分化(j2保守排除解除) =====
    check('tenshi j2A(308)触发(混合段位含low)',
          low_bit('tenshi', 308) == 1.0)
    check('reimu j2A不触发(blockHigh)', low_bit('reimu', 308) == 0.0)

    # ===== 已测空集=真值(青蛙全中段), 不回落全局表 =====
    check('suwako实测空集(2A不触发)', low_bit('suwako', 303) == 0.0)
    check('suwako 402不触发(空集非回落)', low_bit('suwako', 402) == 0.0)

    # ===== 未注入对手名 → 回落全局假设表(向后兼容) =====
    check('未注入回落: 402触发(遗留假设表)',
          low_bit(None, 402) == 1.0)
    check('未注入回落: 303触发', low_bit(None, 303) == 1.0)

    # ===== 表外角色名 → 回落 =====
    check('表外角色回落全局', low_bit('nonexistent_char', 402) == 1.0)

    # ===== 5A(300)任何角色都不触发(中段) =====
    check('5A(300)不触发', low_bit('suika', 300) == 0.0)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
