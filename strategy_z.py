# -*- coding: utf-8 -*-
"""task-80 策略向量 z 接口骨架（env 默认 0，逐位等价；不训练/不部署）.

z 维度（0..1）: aggression, goal_push, goal_burst, distance, resource, risk
env `TH123_STRATEGY_Z` 默认 0/空；=1 才解析；解析失败→禁用（不静默猜）。
"""
import os

DIMS = ('aggression', 'goal_push', 'goal_burst', 'distance', 'resource',
        'risk')


def enabled(env=None):
    v = str(os.environ.get('TH123_STRATEGY_Z', '0') if env is None else env)
    return v.strip() not in ('', '0')


def parse(env=None):
    """'0.7,0.8,0.2,0.5,0.4,0.3' → dict; 非法→None(禁用)."""
    v = str(os.environ.get('TH123_STRATEGY_Z', '') if env is None else env).strip()
    if v in ('', '0'):
        return None
    parts = [p.strip() for p in v.split(',')]
    if len(parts) != len(DIMS):
        return None
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return None
    if any(not (0.0 <= x <= 1.0) for x in vals):
        return None
    return dict(zip(DIMS, vals))


def condition(z=None):
    """env=0/非法 → None（旧行为）；否则返回 z dict 供条件化策略使用."""
    if not enabled() and z is None:
        return None
    if z is None:
        z = parse()
    if z is None:
        return None
    return dict(z)
