# -*- coding: utf-8 -*-
"""task-20 Phase1 进攻类奖励单测(R-a/R-d/R-e; 纯函数, 无外部依赖)."""
import importlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import atk_v1 as A  # noqa: E402

FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


class _P:
    """最小 self 桩: 只挂 _atk 状态。"""
    pass


def _mk():
    p = _P()
    A.reset_state(p)
    return p


def _cls(name, libs=None):
    return {'a': 'MELEE', 'b': 'BULLET', 'c': 'SKILL', 'd': 'MOVE'}.get(name, 'OTHER')


print('== task-20 atk_v1 ==')
chk('默认开 + 参数默认值', A.REW_ATK and
    abs(A.R_PUNISH - 0.10) < 1e-9 and A.WINDOW == 60 and A.CONFIRM == 30
    and abs(A.BIAS - 0.2) < 1e-9 and A.BIAS_DECAY == 800)
chk('attack_macro 分类', A.attack_macro('a', _cls)
    and A.attack_macro('b', _cls) and A.attack_macro('c', _cls)
    and not A.attack_macro('d', _cls))

# R-d 距离/窗口
chk('空挥: 非窗口近距 ×1.2', abs(A.whiff_mult(200, False, 'MELEE') - 1.2) < 1e-9)
chk('空挥: 窗口内不加重 ×1.0', abs(A.whiff_mult(200, True, 'MELEE') - 1.0) < 1e-9)
chk('空挥: 远距射击 ×0.5', abs(A.whiff_mult(500, False, 'BULLET') - 0.5) < 1e-9)
chk('空挥: 远距近战 ×1.2', abs(A.whiff_mult(500, False, 'MELEE') - 1.2) < 1e-9)
chk('空挥: 中距不变 ×1.0', abs(A.whiff_mult(300, False, 'MELEE') - 1.0) < 1e-9)

# R-a 窗口
p = _mk()
chk('窗口: 对手出招 300-598 → True',
    A.window_active({'action': 350}, p._atk, 10))
chk('窗口: 出招后 60F 内恢复窗 → True',
    A.window_active({'action': 0}, p._atk, 40))
chk('窗口: 出招后 61F → False',
    not A.window_active({'action': 0}, p._atk, 71))
chk('窗口: 对手 untech>0 → True',
    A.window_active({'action': 0, 'untech': 5}, p._atk, 80))
chk('窗口: 对手 guardstun(150-158) → True',
    A.window_active({'action': 152}, p._atk, 90))

# R-a 成功才结算
p = _mk()
p._atk.update({'in_window': True, 't': 5})
p._atk['pending'] = {'t': 5, 'dx': 100.0}
r = A.step(p, {}, {'action': 0}, 0, 0, 6)     # 未命中
chk('R-a: 未命中不结算', abs(r) < 1e-12 and p._atk['hits'] == 0)
r = A.step(p, {}, {'action': 0}, 0, 3, 7)     # 命中
chk('R-a: 命中结算 +0.10', abs(r - A.R_PUNISH) < 1e-9
    and p._atk['hits'] == 1 and p._atk['pending'] is None)
p = _mk()
p._atk['pending'] = {'t': 0, 'dx': 100.0}
A.step(p, {}, {'action': 0}, 0, 0, A.CONFIRM + 1)   # 超时
chk('R-a: 超时算空挥/不结算', p._atk['whiffs'] == 1
    and p._atk['hits'] == 0)

# R-e 登记/去重/bias 范围
p = _mk()
p._atk['in_window'] = True
A.on_decision(p, 'a', 100, _cls)
chk('R-e: 窗口内攻击起手登记 attempt', p._atk['attempts'] == 1
    and p._atk['pending'] is not None)
A.on_decision(p, 'a', 100, _cls)
chk('R-e: 同窗只登记一次', p._atk['attempts'] == 1)
p2 = _mk()
p2._atk['in_window'] = False
A.on_decision(p2, 'a', 100, _cls)
chk('R-e: 非窗口不登记', p2._atk['attempts'] == 0)
p3 = _mk()
p3._atk['in_window'] = True
A.on_decision(p3, 'a', 999, _cls)
chk('R-e: 超距不登记', p3._atk['attempts'] == 0)

chk('bias: 起点=0.2', abs(A.bias_now(0, {'u0': 0}) - 0.2) < 1e-9)
chk('bias: 400upd→0.1', abs(A.bias_now(400, {'u0': 0}) - 0.1) < 1e-9)
chk('bias: 800upd→0 之后不为负', A.bias_now(2000, {'u0': 0}) == 0.0)

p = _mk()
p._atk['in_window'] = True
arr = A.bias_for(p, 0, [True, False, True], 3, _cls, ['a', 'd', 'b'])
chk('bias_for: 仅未掩码攻击宏', arr is not None and arr[0] > 0
    and arr[1] == 0.0 and arr[2] > 0)
p._atk['in_window'] = False
chk('bias_for: 非窗口 None', A.bias_for(p, 0, [True] * 3, 3, _cls,
                                        ['a', 'b', 'c']) is None)

# 总开关关闭 = 旧行为
os.environ['TH123_REW_ATK'] = '0'
importlib.reload(A)
chk('关闭: REW_ATK=0', not A.REW_ATK)
chk('关闭: 空挥 ×1.0', A.whiff_mult(200, False, 'MELEE') == 1.0)
chk('关闭: bias=0', A.bias_now(0, {'u0': 0}) == 0.0)
p = _mk()
p._atk['pending'] = {'t': 0, 'dx': 100.0}
chk('关闭: 不结算', A.step(p, {}, {'action': 0}, 0, 5, 1) == 0.0
    and p._atk['hits'] == 0)
os.environ['TH123_REW_ATK'] = '1'
importlib.reload(A)

# ---- 红线①: bias 必须进入 actor 采样 stored_logp(行为概率) ----
import numpy as np  # noqa: E402
import ppo  # noqa: E402

_t = ppo.PPOTrainer(n_side=300, n_out=3)
_t.init_fresh(ppo.TRUNK_FLAT)
_xt = np.zeros((1, 3, 60, 80), dtype=np.float32)
_st = np.zeros((1, 300), dtype=np.float32)
_b = np.array([0.2, -0.1, 0.05], dtype=np.float32)
for _temp in (1.0, 2.0):
    _p0 = _t._pi_forward(_xt, _st, temp=_temp, bias=None)[2][0]
    _pb = _t._pi_forward(_xt, _st, temp=_temp, bias=_b)[2][0]
    _exp = np.exp(np.log(_p0) + _b / _temp)
    _exp = _exp / _exp.sum()
    chk('红线①: bias 后 stored 概率 == softmax(log p + b/temp) '
        '(temp=%s)' % _temp,
        float(np.abs(_pb - _exp).max()) < 1e-6)
    chk('红线①: 无 bias 概率仍归一(temp=%s)' % _temp,
        abs(float(_p0.sum()) - 1.0) < 1e-6)

_src = io.open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'actor_worker.py'), encoding='utf8').read()
_seg = _src[_src.find('def rec_logp'):]
_seg = _seg[:_seg.find('_fleet_logp_rec')]
chk('红线①: actor rec_logp 采样概率用 bias=nbias', 'bias=nbias' in _seg)

print('==== task-20 atk_v1: %d PASS / %d FAIL ===='
      % (30 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
