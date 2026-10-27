# -*- coding: utf-8 -*-
"""task-71 表达力 v1 骨架: 全 6键×9方向×时长档 残差动作空间.

默认 env `TH123_ACT_RESID=0`（未接线, 逐位等价旧行为）；`=1` 才启用编码/采样。
本模块仅提供动作空间/编码/coverage 工具，不修改现有训练/推理路径（W4 迁移时统一接）。
"""
import os

KEYS = ('A', 'B', 'C', 'dash', 'AB', 'BC')          # 6 键
DIRS = (5, 8, 2, 4, 6, 7, 9, 1, 3)                  # 9 方向(中立/8向)
DURATIONS = (1, 2, 3, 4, 6, 8, 10, 12, 16)          # 时长档
N_ACTIONS = len(KEYS) * len(DIRS) * len(DURATIONS)  # 486

KEY_ID = {k: i for i, k in enumerate(KEYS)}
DIR_ID = {d: i for i, d in enumerate(DIRS)}
DUR_ID = {d: i for i, d in enumerate(DURATIONS)}


def resid_enabled(env=None):
    """默认 0/未接线 → False; 仅 =1 启用."""
    v = str(os.environ.get('TH123_ACT_RESID', '0') if env is None else env)
    return v.strip() == '1'


def encode(key, direction, dur):
    return (KEY_ID[key] * len(DIRS) + DIR_ID[direction]) * len(DURATIONS) \
        + DUR_ID[dur]


def decode(a):
    d = int(a)
    dur = DURATIONS[d % len(DURATIONS)]
    d //= len(DURATIONS)
    direction = DIRS[d % len(DIRS)]
    key = KEYS[d // len(DIRS)]
    return key, direction, dur


def all_actions():
    for k in KEYS:
        for d in DIRS:
            for du in DURATIONS:
                yield encode(k, d, du)


def coverage(actions):
    """已覆盖 (key,dir,dur) 数/总 486."""
    s = set(actions)
    return {'unique': len(s), 'total': N_ACTIONS,
            'rate': round(len(s) / N_ACTIONS, 4)}


def apply_if_enabled(base_action, resid_id, env=None):
    """env=0 → 原样返回 base（逐位等价）；env=1 → 残差覆盖."""
    if not resid_enabled(env):
        return base_action
    return {'base': base_action, 'resid': decode(resid_id)}
