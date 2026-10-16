# -*- coding: utf-8 -*-
"""JZ-2/JZ-3: 攻击等级硬直表驱动的帧差纯函数 (frame_adv).

数据源: data/guide_tables/attack_level_stun.json
  (CHM内嵌图片视觉转录+system.txt行内文字双源, 2026-10-14)。
公式(综合攻略outline_73, zonghe.txt line 1253):
  我方硬直差 = 对方防御硬直(正防/错防) − 我方(终了 − 发生)
  正→攻击方先动, 负→防御方先动。
COUNTER: 被攻击硬直上升一个攻击等级(SF大全outline_37)。
回归锚: 萃香近A(等级中/发生9/终了26) 正防=15-(26-9)=-2F, 错防=19-(26-9)=+2F
  (攻略自测吻合, zonghe.txt line 1253)。
"""
import json
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_ROOT, 'data', 'guide_tables',
                       'attack_level_stun.json'), encoding='utf8') as _f:
    _T = json.load(_f)

LEVELS = [r['level'] for r in _T['numeric_table']['rows']]
_HIT = {r['level']: r['hit'] for r in _T['numeric_table']['rows']}
_GUARD = {r['level']: r['guard'] for r in _T['numeric_table']['rows']}
_GUARD_MISS = {r['level']: r['guard_miss'] for r in _T['numeric_table']['rows']}
AIR_GUARD = _T['rules']['air_guard_stun']['frames']      # 19F 固定


def hit_stun(level, counter=False):
    """命中后仰帧数; counter=True时上升一个攻击等级."""
    return _HIT[_bump(level) if counter else level]


def guard_stun(level, correct=True):
    """防御硬直: correct=True正防 / False错防."""
    return (_GUARD if correct else _GUARD_MISS)[level]


def frame_advantage(total, startup, level, correct=True, counter=False):
    """打防后我方硬直差(正=我方有利).

    total=终了(出招到收招总帧), startup=发生帧, level=攻击等级。
    counter只影响命中侧, 打防场景不升档(SF大全: COUNTER是命中概念),
    参数保留以显式表达该语义。
    """
    if counter:
        raise ValueError('COUNTER升档仅作用于命中硬直, 打防无counter')
    return guard_stun(level, correct) - (total - startup)


def _bump(level):
    i = LEVELS.index(level)
    if i + 1 >= len(LEVELS):
        return level            # 特大已顶格
    return LEVELS[i + 1]


def _selftest():
    assert AIR_GUARD == 19
    assert _HIT == {'小': 10, '中': 17, '大': 24, '特大': 34}
    assert _GUARD == {'小': 9, '中': 15, '大': 21, '特大': 27}
    assert _GUARD_MISS == {'小': 11, '中': 19, '大': 27, '特大': 31}
    # 萃香近A回归锚(攻略line 1253自测吻合)
    assert frame_advantage(26, 9, '中', correct=True) == -2
    assert frame_advantage(26, 9, '中', correct=False) == 2
    # COUNTER升档: 中命中17 → 大命中24
    assert hit_stun('中') == 17 and hit_stun('中', counter=True) == 24
    print('frame_adv selftest: OK (%d等级, 空防%dF)' % (len(LEVELS), AIR_GUARD))


if __name__ == '__main__':
    _selftest()
