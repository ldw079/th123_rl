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
# 2026-10-24: 过注册修复 — ONCE(每硬直段仅1次登记) / NO_OVERWRITE(pending 时不再覆盖)
BUFFER_ONCE = os.environ.get('TH123_BUFFER_ONCE', '0') != '0'
BUFFER_NO_OVERWRITE = os.environ.get(
    'TH123_BUFFER_NO_OVERWRITE', '0') != '0'


class BufferState:
    """单训练实例的缓冲状态机(纯逻辑, 可单测)."""

    def __init__(self, names, max_wait=None, extra_allowed=None,
                 once=None, no_overwrite=None):
        self.names = list(names)
        _extra = set(extra_allowed or ())
        self.allowed = {i for i, n in enumerate(self.names)
                        if n in BUFFER_NAMES or n in _extra}
        _mw = os.environ.get('TH123_BUFFER_MAXWAIT')
        if max_wait is not None:
            self.max_wait = int(max_wait)
        elif _mw is not None:
            self.max_wait = int(_mw)
        else:
            self.max_wait = max(BUFFER_K, 40)   # 决策数上限(硬直20-30F; 6 会大量丢弃)
        self.once = BUFFER_ONCE if once is None else bool(once)
        self.no_overwrite = (BUFFER_NO_OVERWRITE if no_overwrite is None
                             else bool(no_overwrite))
        self.seg_id = 0          # 硬直段 ID(上升沿+1; ONCE 判据)
        self._prev_stun = False
        self._reg_seg = -1
        self.once_block = 0
        self.ow_block = 0
        # task-56 加严: mask_blocked 后决策数 / 其中最终=待机(强制 idle)数
        self.blk_n = 0
        self.blk_idle = 0
        self.pending = None      # (mid, frames_waited, dir)
        self.executed = 0
        self.dropped = 0
        self.registered = 0
        self.acted_ok = 0
        self.acted_n = 0
        self.dir_f = 0   # task-48: 方向令牌统计
        self.dir_b = 0
        self.dir_n = 0
        self.drop_to = 0   # P1-2: 超时丢弃
        self.drop_ow = 0   # P1-2: 覆盖丢弃
        self.rehit_n = 0   # P1-2: 执行后8决策内受创统计
        self.rehit_ok = 0

    @property
    def active(self):
        return self.pending is not None

    def update_stun(self, in_stun):
        """每决策调用: 硬直段上升沿 → seg_id+1; 返回 seg_id."""
        in_stun = bool(in_stun)
        if in_stun and not self._prev_stun:
            self.seg_id += 1
        self._prev_stun = in_stun
        return self.seg_id

    def mask_blocked(self):
        """True=屏蔽方向令牌/受身/跳跃/5A(本段已登记过 或 pending 存在)."""
        if self.once and self._reg_seg == self.seg_id:
            return True
        if self.no_overwrite and self.pending is not None:
            return True
        return False

    def note_block(self, is_idle):
        """每次 mask_blocked=True 的决策调用; is_idle=最终动作是否待机."""
        self.blk_n += 1
        if is_idle:
            self.blk_idle += 1

    def register(self, mid, in_stun, direction=None):
        """stun 帧选中 buf 槽 → 登记; 返回 True=已吞掉该决策."""
        if not in_stun or mid not in self.allowed:
            return False
        if self.once and self._reg_seg == self.seg_id:
            self.once_block += 1
            return False
        if self.no_overwrite and self.pending is not None:
            self.ow_block += 1
            return False
        if self.pending is not None:
            self.dropped += 1
            self.drop_ow += 1
        self.pending = (int(mid), 0, direction)
        self.registered += 1
        if self.once:
            self._reg_seg = self.seg_id
        if direction == 'forward':
            self.dir_f += 1
        elif direction == 'back':
            self.dir_b += 1
        else:
            self.dir_n += 1
        return True

    def resolve(self, in_stun):
        """每决策调用: 若已解硬直→返回待执行 mid(并清空); 否则 None."""
        if self.pending is None:
            return None
        mid, waited, _dir = self.pending
        if in_stun:
            self.pending = (mid, waited + 1, _dir)
            if waited + 1 > self.max_wait:
                self.dropped += 1
                self.drop_to += 1
                self.pending = None
            return None
        self.pending = None
        self.executed += 1
        return mid, _dir

    def note_outcome(self, acted, rehit=False):
        """执行后 8 决策内: 出现非待机动作(acted) / 是否受创(rehit8)."""
        self.acted_n += 1
        if acted:
            self.acted_ok += 1
        self.rehit_n += 1
        if rehit:
            self.rehit_ok += 1
        return acted

    def stats_line(self):
        return ('[buffer] registered=%d executed=%d dropped=%d '
                'drop_to=%d drop_ow=%d acted=%d/%d rehit8=%d/%d '
                'dir_f=%d dir_b=%d dir_n=%d segs=%d '
                'once_block=%d ow_block=%d blk_idle=%d/%d'
                % (self.registered, self.executed, self.dropped,
                   self.drop_to, self.drop_ow,
                   self.acted_ok, self.acted_n,
                   self.rehit_ok, self.rehit_n,
                   self.dir_f, self.dir_b, self.dir_n,
                   self.seg_id, self.once_block, self.ow_block,
                   self.blk_idle, self.blk_n))
