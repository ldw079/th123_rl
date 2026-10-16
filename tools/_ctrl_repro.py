# -*- coding: utf-8 -*-
"""一次性: 对照臂NoneType.T复现 — 进程内跑trainer首局, 异常裸抛."""
import os
import sys
import traceback

os.environ['TH123_STORE'] = r'D:\temp\th123_models_control'
sys.path.insert(0, r'D:\temp\th123_rl_control')
sys.stdout.reconfigure(encoding='utf8')

import train_tm as T

tr = T.TMTrainer('reimu', 21080, tps=360, episodes=1, vs_com=False,
                 fleet_mode=True)
try:
    tr.train()
except Exception:
    traceback.print_exc()
