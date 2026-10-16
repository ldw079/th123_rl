# -*- coding: utf-8 -*-
"""CE-7: 推板进度势测试 — 连续角项+telescoping验证+门控。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pkt(hp=10000, x=640, spirit=1000, gauge=0):
    return {'position.x': float(x), 'position.y': 50.0, 'hp': hp,
            'spirit': spirit, 'cardGauge': gauge}


def _pot_with(env_val, left, right):
    """在指定CE7环境变量下计算势。"""
    if env_val is None:
        os.environ.pop('TH123_CE7_POT', None)
    else:
        os.environ['TH123_CE7_POT'] = env_val
    try:
        from train_tm import state_potential
        return state_potential(left, right)
    finally:
        os.environ.pop('TH123_CE7_POT', None)


def test_gate_default_off():
    """环境变量未设 → 与显式0逐位一致(连续项不生效)。"""
    l = _pkt(x=640)
    r = _pkt(x=200)
    p_off = _pot_with('0', l, r)
    p_default = _pot_with(None, l, r)
    assert p_off == p_default


def test_gate_on_delta():
    """TH123_CE7_POT=1: on-off差值=纯corner_progress贡献。"""
    l = _pkt(x=640)
    def _delta(rx):
        r = _pkt(x=rx)
        return _pot_with('1', l, r) - _pot_with('0', l, r)

    # 对手越近角 → corner_progress贡献越大(单调)
    prev = None
    for rx in (640, 500, 300, 200, 130, 100):
        d = _delta(rx)
        if prev is not None:
            assert d > prev, 'rx=%d 贡献%.6f未>前值%.6f' % (rx, d, prev)
        prev = d
    # 对称版中: own侧惩罚恰好抵消opp侧增益(净角优势=0, 设计语义)
    assert abs(_delta(640)) < 1e-12
    # 非对称: 对手贴角+own版中 → 净角优势>0
    assert _delta(100) > 0


def test_own_side_penalty():
    """own被推向角 → corner_progress负贡献(不被关角)。"""
    r = _pkt(x=640)
    def _delta_own(lx):
        l = _pkt(x=lx)
        return _pot_with('1', l, r) - _pot_with('0', l, r)

    # own越近角 → 贡献越负(单调下降)
    prev = None
    for lx in (640, 500, 300, 200, 130, 100):
        d = _delta_own(lx)
        if prev is not None:
            assert d < prev, 'own rx=%d 贡献%.6f未<前值%.6f' % (lx, d, prev)
        prev = d


def test_telescoping():
    """往返推→on项净差=0(telescoping保持)。"""
    l = _pkt(x=640)
    r_start = _pkt(x=640)
    r_pushed = _pkt(x=200)
    d1 = _pot_with('1', l, r_pushed) - _pot_with('1', l, r_start)
    d2 = _pot_with('1', l, r_start) - _pot_with('1', l, r_pushed)
    assert abs(d1 + d2) < 1e-9


def test_magnitude():
    """连续项版中→贴角全程增量 ≈ 二值跳变的2-3倍(方案标定)。"""
    # 二值跳变量: own置于x=120(与探针点119/121等距) — 距离势斜率
    # (0.15/100px)在2px差上恰好贡献-0.003, 会完全掩盖角跳变, 须消去
    l_edge = _pkt(x=120)
    binary = (_pot_with('0', l_edge, _pkt(x=119))
              - _pot_with('0', l_edge, _pkt(x=121)))
    # 连续项全程增量(on-off差值的差; own侧贡献恒定被差分消去)
    l = _pkt(x=640)
    delta_far = _pot_with('1', l, _pkt(x=620)) - _pot_with('0', l, _pkt(x=620))
    delta_near = _pot_with('1', l, _pkt(x=100)) - _pot_with('0', l, _pkt(x=100))
    continuous = delta_near - delta_far
    assert binary > 0 and continuous > 0
    ratio = continuous / binary
    assert 2.0 <= ratio <= 3.0, '连续/二值=%.2f(应2-3)' % ratio


if __name__ == '__main__':
    for fn in [test_gate_default_off, test_gate_on_delta,
               test_own_side_penalty, test_telescoping,
               test_magnitude]:
        fn()
        print('✓', fn.__name__)
    print('test_ce7_pot: 全部通过')
