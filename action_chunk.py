# -*- coding: utf-8 -*-
"""task-72 动作 chunk 骨架（与 task-71 残差/时长档对齐; env 默认 0 不改变行为）.

Chunk schema:
  {'kind': 'macro'|'resid', 'slot': int|None, 'frames': int,
   'resid_seq': [action_id...], 'interrupt_at': [frame...] }
env `TH123_ACTION_CHUNK=0` 默认：返回 None（旧逐决策路径）；=1 才构造 chunk。
"""
import os

MAX_FRAMES = 16
DURATIONS = (1, 2, 3, 4, 6, 8, 10, 12, 16)


def enabled(env=None):
    v = str(os.environ.get('TH123_ACTION_CHUNK', '0') if env is None else env)
    return v.strip() == '1'


def make_macro_chunk(slot, frames, interrupt_at=None):
    if not (1 <= int(frames) <= MAX_FRAMES):
        raise ValueError('frames 1..%d' % MAX_FRAMES)
    return {'kind': 'macro', 'slot': int(slot), 'frames': int(frames),
            'resid_seq': [], 'interrupt_at': list(interrupt_at or [])}


def make_resid_chunk(resid_seq):
    seq = [int(x) for x in resid_seq]
    if not seq:
        raise ValueError('resid_seq empty')
    return {'kind': 'resid', 'slot': None, 'frames': len(seq),
            'resid_seq': seq, 'interrupt_at': []}


def validate(chunk):
    if chunk.get('kind') not in ('macro', 'resid'):
        raise ValueError('kind')
    if not (1 <= int(chunk.get('frames', 0)) <= MAX_FRAMES):
        raise ValueError('frames')
    if chunk['kind'] == 'macro' and chunk.get('slot') is None:
        raise ValueError('macro slot')
    if chunk['kind'] == 'resid' and len(chunk.get('resid_seq') or []) != \
            int(chunk.get('frames', 0)):
        raise ValueError('resid_seq/frames mismatch')
    for f in chunk.get('interrupt_at') or []:
        if not (0 <= int(f) < int(chunk['frames'])):
            raise ValueError('interrupt_at out of range')
    return True


def build_if_enabled(kind, **kw):
    if not enabled():
        return None
    c = make_macro_chunk(**kw) if kind == 'macro' else \
        make_resid_chunk(**kw)
    validate(c)
    return c
