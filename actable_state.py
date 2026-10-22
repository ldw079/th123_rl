# -*- coding: utf-8 -*-
"""actable_state.py — stun/起身可动窗状态估计(纯逻辑, task-30 stage1).

无帧表: 用 episode 内已观测同类 stun 长度在线估计剩余硬直; 输出
frames_in_stun / est_left / near_end(<=2F) / actable。
env `TH123_ACTABLE`(默认0) 用于训练接线(仅埋点, 不改特征维度)。
"""
from __future__ import annotations

import os

ACTABLE = os.environ.get('TH123_ACTABLE', '0') != '0'
HIT_LO, HIT_HI = 50, 78
GUARD_LO, GUARD_HI = 150, 166


def is_stun(action):
    a = int(action or 0)
    return (HIT_LO <= a <= HIT_HI) or (GUARD_LO <= a <= GUARD_HI)


class ActableTracker:
    def __init__(self, near=2):
        self.near = int(near)
        self.frames_in_stun = 0
        self.last_len = 0
        self.avg_len = 0.0
        self._n = 0
        self.actable = True
        self.in_stun = False

    def update(self, action):
        """每帧/决策调用; 返回特征 dict."""
        st = is_stun(action)
        if st:
            self.frames_in_stun += 1
            self.in_stun = True
        else:
            if self.in_stun and self.frames_in_stun > 0:
                self.last_len = self.frames_in_stun
                self._n += 1
                self.avg_len = ((self.avg_len * (self._n - 1)
                                 + self.last_len) / self._n)
            self.frames_in_stun = 0
            self.in_stun = False
        est_left = (max(0.0, self.avg_len - self.frames_in_stun)
                    if self.in_stun else 0.0)
        near_end = bool(self.in_stun and est_left <= self.near)
        actable = (not self.in_stun)
        self.actable = actable
        return {'frames_in_stun': self.frames_in_stun,
                'est_left': round(est_left, 2),
                'near_end': int(near_end),
                'actable': int(actable)}

    def line(self):
        return ('[actable] in_stun=%d frames=%d est_left=%.2f near_end=%d '
                'actable=%d avg=%.2f' % (
                    int(self.in_stun), self.frames_in_stun,
                    max(0.0, self.avg_len - self.frames_in_stun)
                    if self.in_stun else 0.0, 0, int(self.actable),
                    self.avg_len))
