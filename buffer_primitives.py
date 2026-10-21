# -*- coding: utf-8 -*-
"""buffer_primitives.py — 硬直末预输入缓冲原语(task-29/30 阶段1).

语义(阶段1, 无帧数据表):
- 仅在 stun 帧(受创 50-78 / 正防 150-157 / 158-166)允许登记 "buf 槽" 动作
  (槽复用现有宏: 跳跃/5A, 不扩动作空间);
- 登记后吞掉该决策(执行 待机); 在检测到 action 离开 stun 的首帧,
  立即执行登记的宏(等价 end+0; 探针已证 end-10 内输入有效, 属保守安全侧);
- 登记后超过 max_wait 决策仍未解硬直 → 丢弃(防过期输入);
- env `TH123_BUFFER=0` 时 gate 不启用(旧行为), BufferState 不被调用.

设计注: Lead 期望 end-K 预启; v1 无帧表无法估计剩余硬直, 先实现 end+0 执行
(等价"硬直一结束就出招"), K 保留为 max_wait/后续帧表接入的扩展位.
"""
from __future__ import annotations

import os

BUFFER = os.environ.get('TH123_BUFFER', '0') != '0'
BUFFER_K = int(os.environ.get('TH123_BUFFER_K', '6'))
# 允许缓冲的宏名(槽复用, 不扩动作空间). 按角色可配置(缺失则跳过)。
BUFFER_NAMES = tuple(
    n for n in os.environ.get('TH123_BUFFER_NAMES', '跳跃,5A').split(',') if n)


class BufferState:
    """单训练实例的缓冲状态机(纯逻辑, 可单测)."""

    def __init__(self, names, max_wait=None):
        self.names = list(names)
        self.allowed = {i for i, n in enumerate(self.names)
                        if n in BUFFER_NAMES}
        _mw = os.environ.get('TH123_BUFFER_MAXWAIT')
        if max_wait is not None:
            self.max_wait = int(max_wait)
        elif _mw is not None:
            self.max_wait = int(_mw)
        else:
            self.max_wait = max(BUFFER_K, 40)   # 决策数上限(硬直20-30F; 6 会大量丢弃)
        self.pending = None      # (mid, frames_waited)
        self.executed = 0
        self.dropped = 0
        self.registered = 0
        self.acted_ok = 0
        self.acted_n = 0

    @property
    def active(self):
        return self.pending is not None

    def register(self, mid, in_stun):
        """stun 帧选中 buf 槽 → 登记; 返回 True=已吞掉该决策."""
        if not in_stun or mid not in self.allowed:
            return False
        if self.pending is not None:
            self.dropped += 1
        self.pending = (int(mid), 0)
        self.registered += 1
        return True

    def resolve(self, in_stun):
        """每决策调用: 若已解硬直→返回待执行 mid(并清空); 否则 None."""
        if self.pending is None:
            return None
        mid, waited = self.pending
        if in_stun:
            self.pending = (mid, waited + 1)
            if waited + 1 > self.max_wait:
                self.dropped += 1
                self.pending = None
            return None
        self.pending = None
        self.executed += 1
        return mid

    def note_outcome(self, acted):
        """执行后 8 决策内是否出现非待机动作(行为生效判定)."""
        self.acted_n += 1
        if acted:
            self.acted_ok += 1
        return acted

    def stats_line(self):
        return ('[buffer] registered=%d executed=%d dropped=%d acted=%d/%d'
                % (self.registered, self.executed, self.dropped,
                   self.acted_ok, self.acted_n))
