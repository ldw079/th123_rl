# -*- coding: utf-8 -*-
"""R19(审查2026-10-02): P1/P2视觉栈同构行为测试。
SideDriver._visual_feat必须与train_tm._visual_feat逐字同构
([f2, Δ1, Δ2]差分栈) — 原版P2用3张原始帧, 评估/P2输入全在训练分布外。"""
import os
import sys

sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import numpy as np

from side_driver import SideDriver
from train_tm import TMTrainer


def _fake_frame(seed):
    rng = np.random.default_rng(seed)
    img = np.zeros((60, 80), dtype=np.uint8)
    for _ in range(30):
        img[rng.integers(0, 60), rng.integers(0, 80)] = rng.integers(
            100, 255)
    return img


_l = _fake_frame(1)
_r = _fake_frame(2)
_objs = []

# 期望差分栈(train_tm公式)
f0, f1, f2 = _fake_frame(0), _l, _fake_frame(3)
d1 = np.clip(f2.astype(np.int16) - f1.astype(np.int16), 0, 255).astype(np.uint8)
d2 = np.clip(f1.astype(np.int16) - f0.astype(np.int16), 0, 255).astype(np.uint8)
expect = np.concatenate([f2.ravel(), d1.ravel(), d2.ravel()])

# train_tm栈
tr = TMTrainer.__new__(TMTrainer)
tr.feat_hist = [f0.ravel(), f1.ravel(), f2.ravel()]
got_tr = tr._visual_feat(None, None, None)
assert np.array_equal(got_tr, expect), 'train_tm视觉栈与公式不符'

# SideDriver栈 — 同帧序直填feat_hist(渲染路径在下方单独验)
sd = SideDriver('reimu', 'L')
sd.feat_hist = [f0.ravel(), f1.ravel(), f2.ravel()]
got_sd = sd._visual_feat()
assert got_sd is not None and np.array_equal(got_sd, expect), \
    'SideDriver视觉栈与train_tm不同构(评估分布外, R19)'
# _push_frame: 逐帧追加+5帧上限(同train_tm)
sd.feat_hist = []
_lk = {'position.x': 500.0, 'position.y': 100.0, 'direction': 1,
       'airBorne': False}
_rk = {'position.x': 900.0, 'position.y': 100.0}
for _ in range(7):
    sd._push_frame(_lk, _rk, [])
assert len(sd.feat_hist) == 5, '5帧上限失效: %d' % len(sd.feat_hist)
# 逐帧渲染非恒定(帧间应有差分信号)
assert sd._visual_feat() is not None
# 技能等级查表接线(R19: P2侧_char_name)
assert sd.feat_builder._char_name == 'reimu', 'SideDriver._char_name未设'
# cid_to_slot真表(R19: 原恒None桩; R61f: 合并路径已删—cid歧义)
from skill_levels import cid_to_slot, skill_levels_from_hand
assert cid_to_slot(100) is None and cid_to_slot(103, 'reimu') == 1 \
    and cid_to_slot(110, 'suika') == 3 and cid_to_slot(200) is None \
    and cid_to_slot(102, 'reimu') == 3 and cid_to_slot(102, 'marisa') == 0
_lv0 = skill_levels_from_hand(b'\x64\x02\xff\xff\xff\xff\xff\xff\xff\xff',
                              [0, 0, 0, 0], b'\x64\x03' + b'\xff' * 8,
                              char='reimu')
assert _lv0 == [1, 0, 0, 0], '技能卡消耗应升级槽0, 实际%s' % _lv0
# R32(审查2026-10-02"时间基"): frame_input连续调→帧栈逐帧增长
# (守卫_push_frame在frame_input内而非decide内 — 形态+时间基双守卫)
# 注: 只验帧栈增长, 不走decide全链(需完整状态包)
sd_tb = SideDriver('reimu', 'L')
sd_tb.feat_hist = []
for _ in range(6):
    sd_tb._push_frame(_lk, _rk, [])
assert len(sd_tb.feat_hist) == 5, \
    '帧栈未逐帧增长: %d — _push_frame不在frame_input内?' % len(sd_tb.feat_hist)
# 决定性: decide()源码不含_push_frame/feat_hist.append
import re as _re2
_sd_src = open(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                  'side_driver.py'), encoding='utf-8').read()
_dec_m = _re2.search(r'    def decide\(self.*?(?=\n    def |\n\nclass |\Z)',
                    _sd_src, _re2.S)
_dec_body = _dec_m.group(0) if _dec_m else ''
assert '_push_frame' not in _dec_body and 'feat_hist.append' not in _dec_body, \
    'decide()内含推帧代码(时间基回退!)'
_fi_m = _re2.search(r'    def frame_input\(self.*?(?=\n    def |\n\nclass |\Z)',
                   _sd_src, _re2.S)
assert _fi_m and 'self._push_frame' in _fi_m.group(0), \
    'frame_input()内无_push_frame(时间基断线!)'
print('✓ 时间基: frame_input推帧+decide不推(源码级断言)')
print('✓ P1/P2视觉栈同构 + _char_name + cid_to_slot真表 + 时间基')
print('\n视觉栈同构行为测试通过 ✓')
