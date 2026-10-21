# -*- coding: utf-8 -*-
"""Gen-1(2026-10-19): 决策历史记忆 v1 — 编解码/缓冲/网络分支.

env:
  TH123_MEM_DECISIONS  默认 0(旧行为; 不实例化分支) / 实验档 8
  TH123_VAL_DEACT      默认 0 / 1(值头屏蔽 side 前 2N 上一动作 one-hot)
数据(每决策 ~24B): hist int8 [n_dec, 8, 3]
  [:,0] 我方宏类别 0-6: MELEE/SKILL/BULLET/MOVE/GUARD/JUMP/OTHER
  [:,1] 我方结果 0=none/1=hit/2=blocked/3=whiff (决策后 60F 归因回填)
  [:,2] 敌方动作类 0-7 低 3 位 | 事件位: startup=8 recovery=16 guardstun=32 untech=64
全局 3 维: my_in_punish, opp_in_punish, combo_count/7
"""
from __future__ import annotations

import os

MEM_DECISIONS = int(os.environ.get('TH123_MEM_DECISIONS', '0'))
VAL_DEACT = int(os.environ.get('TH123_VAL_DEACT', '1')) != 0
MEM_N = 8
MEM_BYTES = 3
HIST_DIM = MEM_N * MEM_BYTES          # 24
GLOBAL_DIM = 3
MEM_IN = HIST_DIM + GLOBAL_DIM        # 27
MEM_HID = 32
MEM_OUT = 64

ACT_MELEE, ACT_SKILL, ACT_BULLET = 300, 400, 500
EV_STARTUP, EV_RECOVERY = 8, 16
EV_GUARDSTUN, EV_UNTECH = 32, 64


def my_class(action):
    """我方宏类别 0-6(输入=游戏动作 id 或宏名类)。"""
    a = int(action or 0)
    if 300 <= a < 400:
        return 0
    if 400 <= a < 450:
        return 1
    if 450 <= a < 600:
        return 2
    if 150 <= a <= 158:
        return 4
    if 128 <= a < 300:
        return 6
    return 3          # 移动/待机/其他


def opp_class(action):
    """敌方动作类 0-7(粗分桶, 与 opp_model 上下文一致)。"""
    a = int(action or 0)
    if 150 <= a <= 158:
        return 1      # guard
    if 128 <= a < 150:
        return 2      # hitstun
    if 159 < a < 300:
        return 3      # down/untech
    if 300 <= a < 400:
        return 4      # melee
    if 400 <= a <= 599:
        return 5      # bullet/skill
    if 128 <= a:
        return 6
    return 7 if a >= 600 else 0


def opp_events(opp_action=0, opp_untech=0):
    """敌方事件位(startup/recovery/guardstun/untech 可并存)。"""
    a = int(opp_action or 0)
    ev = 0
    if 300 <= a <= 598:
        ev |= EV_STARTUP
    if int(opp_untech or 0) > 0:
        ev |= EV_UNTECH
    if a in range(150, 159):
        ev |= EV_GUARDSTUN
    else:
        ev |= EV_RECOVERY if 128 <= a < 300 else 0
    return ev


def hist_step(my_action=0, my_outcome=0, opp_action=0, opp_untech=0):
    return (int(my_class(my_action)) & 0x7,
            int(my_outcome) & 0x3,
            (int(opp_class(opp_action)) & 0x7) | (opp_events(opp_action,
                                                             opp_untech) & 0x78))


def zeros_hist(n_dec, n=MEM_N):
    import numpy as np
    return np.zeros((int(n_dec), n, MEM_BYTES), dtype=np.int8)


def encode_global(my_punish, opp_punish, combo):
    import numpy as np
    return np.array([[1.0 if my_punish else 0.0,
                      1.0 if opp_punish else 0.0,
                      min(int(combo), 7) / 7.0]], dtype=np.float32)


def flatten_hist(hist):
    """(n_dec,8,3) int8 → (n_dec,27) float32 网络输入(含全局段由外部填)."""
    import numpy as np
    h = np.asarray(hist)
    return h.reshape(h.shape[0], -1).astype(np.float32) / 7.0


def zeros_mem_input(n):
    import numpy as np
    return np.zeros((int(n), MEM_IN), dtype=np.float32)


def window_hist(steps, n=MEM_N):
    """最近 n 步单步编码(3,) → (n,3) int8, 左侧零填充(旧→新)."""
    import numpy as np
    out = np.zeros((n, MEM_BYTES), dtype=np.int8)
    tail = list(steps)[-n:]
    if tail:
        out[n - len(tail):] = np.asarray(tail, dtype=np.int8)
    return out
