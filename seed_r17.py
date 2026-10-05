# -*- coding: utf-8 -*-
"""R17新架构播种: 三角色全新初始化模型落盘 + 对手池快照。"""
import os
import sys

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_tm as T
from ppo import PPOTrainer
from outer_loop import OpponentPool

for ch in ('reimu', 'marisa', 'suika'):
    n = len(T.CHAR_LIBS[ch]['macros'])
    pi = os.path.join(T.STORE_DIR, 'model_ppo_%s.npz' % ch)
    v = pi.replace('.npz', '_v.npz')
    t = PPOTrainer(n_side=2 * n + 308, n_out=n)
    t.init_fresh(2 * n + 308)
    t.save(pi, v)
    print(ch, 'n_out=%d n_side=%d -> %s' % (n, 2 * n + 308, pi))

snap = OpponentPool().snapshot()
print('pool seeded: %s' % [os.path.basename(p) for p in snap])
