# -*- coding: utf-8 -*-
"""P1(审计#6): 池序→角色名映射 20/20 + _side_feat 消费端行为（C15 候选）.

背景: `side_driver._POOL_OPP_NAME` 原为 {游戏角色ID: 名}, 而 `_side_feat` 用
**池序** 查 → sakuya(池11)查到'aya'、suika(池2)查到'sakuya'、扩展区20-27→None,
导致 BH-3.2 `_opp_char`(守备段位表)与 `_jz1_ids`(JZ-1冷却) 对多数非主力对位错表。
修复: 由 `TMTrainer._CHAR_POOL_IDX`(单一事实源)反演 → 20/20 池序→名。
本测试用真实 CHAR_LIBS/SideDriver/_side_feat, 不自造布局。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

import numpy as np  # noqa: E402

from side_driver import SideDriver, _POOL_OPP_NAME  # noqa: E402
from train_tm import CHAR_LIBS, TMTrainer  # noqa: E402

POOL = TMTrainer._CHAR_POOL_IDX
assert len(POOL) == 20, '池映射应 20 条, 实际 %d' % len(POOL)
assert set(_POOL_OPP_NAME.keys()) == set(POOL.values()), \
    '池序键集应=池序值集: %r vs %r' % (sorted(_POOL_OPP_NAME),
                                       sorted(set(POOL.values())))
for _name, _idx in POOL.items():
    assert _POOL_OPP_NAME.get(_idx) == _name, \
        '池序%d 应为 %s, 实际 %r' % (_idx, _name, _POOL_OPP_NAME.get(_idx))
print('✓ _POOL_OPP_NAME 20/20 (池序→名, 由 _CHAR_POOL_IDX 反演)')

# 真实侧特征输入(与训练同构, 不造虚构布局)
_own = {'position.x': 700.0, 'position.y': 100.0, 'spirit': 1500,
        'hp': 9000, 'airBorne': False, 'direction': -1, 'action': 130,
        'cardGauge': 1000, 'score': 0, 'hand': b'\xff' * 10,
        'comboDamage': 0, 'untech': 0, 'timeStop': 0, 'hitStop': 0}
_opp = dict(_own)
_opp.update({'position.x': 400.0, 'direction': 1, 'hp': 8000})
_w = {'active': 3, 'displayed': 3, 'timer': 500}
_bul = []

checked = 0
for _name, _idx in POOL.items():
    d = SideDriver('reimu', 'L')
    got = d.set_opponent(_name)
    assert got == _idx, '%s: set_opponent 应=%d, 实际 %r' % (_name, _idx, got)
    s = d._side_feat(_own, _opp, _w, _bul)
    c = 2 * d.n_macros
    assert len(s) == d.n_side, '侧向量长度应=n_side'
    if _idx <= 19:
        slot = c + 227 + _idx
        assert s[slot] > 0.5, '%s: core[227+%d] 应=1' % (_name, _idx)
        assert abs(float(s[c + 227:c + 247].sum()) - 1.0) < 1e-5, \
            '%s: 对手角色段应恰 1 个槽位' % _name
    else:
        slot = c + 308 + (_idx - 20)
        assert s[slot] > 0.5, '%s: 扩展区 core[308+%d] 应=1' % (_name,
                                                              _idx - 20)
        assert abs(float(s[c + 227:c + 247].sum())) < 1e-5, \
            '%s: 扩展区对手不应写段11槽' % _name
    assert d.feat_builder._opp_char == _name, \
        '%s: _opp_char 应=%s, 实际 %r' % (_name, _name,
                                          d.feat_builder._opp_char)
    assert d.feat_builder._jz1_ids[1] == CHAR_LIBS[_name]['id'], \
        '%s: _jz1_ids 应=%d, 实际 %r' % (_name, CHAR_LIBS[_name]['id'],
                                         d.feat_builder._jz1_ids)
    checked += 1
print('✓ _side_feat 20/20 槽位/_opp_char/_jz1_ids 一致 (checked=%d)' % checked)

# 未知角色: 不猜, 不写槽位
d = SideDriver('reimu', 'L')
assert d.set_opponent('nonexistent_char') is None, '未知角色应返回 None'
s = d._side_feat(_own, _opp, _w, _bul)
assert abs(float(s[2 * d.n_macros + 227:
                   2 * d.n_macros + 247].sum())) < 1e-6, '未知角色不得写槽'
print('✓ 未知角色不猜(返回None, 槽位全零)')

print('\n池序映射行为测试通过 ✓')
