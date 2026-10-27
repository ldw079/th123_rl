# -*- coding: utf-8 -*-
"""W4 slot registry 骨架（一次迁移; env 默认 0 不改变现有行为）.

- 固定容量 C=256; 现有 id 0..N-1 身份映射**保持不变**; 新宏追加空 slot。
- env `TH123_SLOT_REGISTRY=0`（默认）→ 返回旧映射（逐位等价）；=1 才启用 registry。
- 本模块只提供映射/校验/追加，不写模型/不接训练（迁移窗一次接）。
"""
import json
import os

CAPACITY = 256


def enabled(env=None):
    v = str(os.environ.get('TH123_SLOT_REGISTRY', '0') if env is None else env)
    return v.strip() == '1'


def identity_map(macros):
    """env=0 / 旧模型: 原 id→name 映射不变."""
    return {i: n for i, n in enumerate(macros)}


def build(macros, new_macros=(), capacity=CAPACITY):
    """旧 id 保留; 新宏按顺序填第一个空 slot; 容量不足→抛错(不静默截断)."""
    n = len(macros)
    if n > capacity:
        raise ValueError('现有宏数 %d > 容量 %d' % (n, capacity))
    reg = {i: m for i, m in enumerate(macros)}
    used = set(reg)
    free = [i for i in range(capacity) if i not in used]
    added = []
    for m in new_macros:
        if not free:
            raise ValueError('容量 %d 已满, 无法追加 %s' % (capacity, m))
        slot = free.pop(0)
        reg[slot] = m
        added.append({'id': slot, 'name': m})
    manifest = {'schema': 1, 'capacity': capacity, 'n_old': n,
                'n_total': len(reg), 'added': added,
                'registry_version': 1,
                'old_ids_preserved': all(i in reg for i in range(n))}
    return reg, manifest


def validate_model_compat(n_out, capacity=CAPACITY):
    """旧模型输出层 n_out 必须 ≤ 容量; 旧 id 语义不变."""
    if int(n_out) > capacity:
        raise ValueError('模型 n_out=%d > 容量 %d' % (n_out, capacity))
    return True


def load_registry(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)
