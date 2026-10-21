# -*- coding: utf-8 -*-
"""task-39: 评估路径统一 mask / config_error 回退 / 指令技静态表 / masked 埋点 / [mem] 行."""
import importlib
import os
import sys

import numpy as np

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
os.chdir(WT)
FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


print('== task-39 ==')
import game_gates as G  # noqa: E402
NAMES = ['待机', '前进', '5A', '6A', 'jA', 'j6A', '236B', '623B', '214C',
         '22C', '立防', '蹲防', '受身', '起身', '跳跃', '空防', '结界4',
         '空结界4', '卡·铜钱', 'j2B']


def mask_idx(*names):
    return np.array([n in names for n in NAMES], dtype=bool)


# 1) env=0 逐位
os.environ['TH123_ACT_MASK'] = '0'
importlib.reload(G)
m0 = mask_idx('待机', '5A', 'jA')
chk('env=0 逐位返回', np.array_equal(
    G.apply_state_gates(m0, NAMES, {'action': 0, 'airBorne': False}), m0))

# 2) 地面: 空中技/空防被禁; 指令技(数字)保留
os.environ['TH123_ACT_MASK'] = '1'
importlib.reload(G)
mg = G.apply_state_gates(mask_idx(*NAMES), NAMES,
                         {'action': 0, 'airBorne': False})
chk('地面禁空中技', all(not mg[NAMES.index(n)]
                    for n in ('jA', 'j6A', '空防', '空结界4', 'j2B')))
chk('地面保留指令技(静态表)',
    all(mg[NAMES.index(n)] for n in ('236B', '623B', '214C', '22C')))
chk('地面保留地面技/防御/受身',
    all(mg[NAMES.index(n)] for n in ('5A', '6A', '立防', '受身')))

# 3) 空中: 地面技/地面移动/指令技(静态地空表)被禁; 空中技保留
ma = G.apply_state_gates(mask_idx(*NAMES), NAMES,
                         {'action': 0, 'airBorne': True})
chk('空中禁地面技/指令技/地面移动',
    all(not ma[NAMES.index(n)]
        for n in ('5A', '6A', '236B', '623B', '214C', '22C', '跳跃')))
chk('空中保留空中技', all(ma[NAMES.index(n)]
                     for n in ('jA', 'j6A', 'j2B', '空防')))

# 4) 不可动: 受创只放受身; 158 全 mask→仅待机
N4 = ['待机', '受身', '5A', '立防']
G.reset_masked_stats()
m_hit = G.apply_state_gates(np.ones(4, bool), N4,
                           {'action': 60, 'airBorne': False})
chk('受创只放受身', bool(m_hit[1]) and not m_hit[0]
    and not m_hit[2] and not m_hit[3])
m_158 = G.apply_state_gates(np.ones(4, bool), N4,
                           {'action': 158, 'airBorne': False})
chk('158 全 mask→仅待机', bool(m_158[0]) and int(m_158.sum()) == 1)

# 5) masked 埋点计数/格式(局部 names/mask 对齐)
N5 = ['待机', '5A', 'jA']
G.reset_masked_stats()
G.apply_state_gates(np.ones(3, bool), N5,
                    {'action': 0, 'airBorne': True})   # 5A/jA→jA保留,5A被禁
line = G.masked_line()
chk('masked 埋点格式/计数', 'masked=1/1' in line and '%' in line)
G.apply_state_gates(np.ones(3, bool), ['待机', 'jA', '受身'],
                    {'action': 0, 'airBorne': True})   # 无变化
chk('第二次调用 total 递增且 masked 不虚增',
    'masked=1/2' in G.masked_line())

# 6) 空 mask 无待机 → 响亮报错(config_error 由调用方捕获关 gate)
try:
    G.apply_state_gates(np.zeros(3, bool), ['5A', 'jA', '立防'],
                        {'action': 0, 'airBorne': False})
    got_err = False
except RuntimeError:
    got_err = True
chk('配置异常响亮报错', got_err)

# 7) 接线断言(源码级): side_driver/train_tm/learner_hub
sd = open(os.path.join(WT, 'side_driver.py'), encoding='utf8').read()
tt = open(os.path.join(WT, 'train_tm.py'), encoding='utf8').read()
lh = open(os.path.join(WT, 'learner_hub.py'), encoding='utf8').read()
chk('side_driver 接入统一 mask',
    '_dd_gate.apply_state_gates(' in sd and 'config_error' in sd
    and '_eval_gate_cnt' in sd)
chk('train_tm config_error 回退 + masked 日志',
    '[act_mask] config_error -> gates disabled: ' in tt
    and ('masked_choice_line()' in tt or 'masked_line()' in tt)
    and 'note_choice(mid)' in tt and '_act_mask_ok' in tt)
chk('[mem] 启动行', "'[mem] %s mem_dim=%d" in lh)
print('==== task-39: %d PASS / %d FAIL ====' % (16 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
