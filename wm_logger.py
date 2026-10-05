# -*- coding: utf-8 -*-
"""世界模型转移日志器(S1): 每决策拍记录物理状态+双方动作。

数据格式: 每行27维 = [26维物理状态, 1维我方宏ID]
物理状态: 双方坐标/速度/HP/灵力/充能/手牌数 + 距离 + 天气 + 动作ID + 朝向 + 弹幕摘要

用途: 离线训练动力学模型 s'=f(s, my_macro, opp_action) → Dreamer-lite
"""
import os

import numpy as np

WM_STATE_DIM = 26
WM_ROW_DIM = 27   # +宏ID


class WMLogger:
    """累积转移数据, 批末保存到 npz (保留最近50000条)。"""

    def __init__(self, path, side_tag=""):
        self.path = path
        self.tag = side_tag
        self.rows = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        if os.path.exists(self.path):
            try:
                old = np.load(self.path)
                self.rows = old["T"].tolist()
            except Exception:
                self.rows = []
        self._loaded = True

    def log(self, own_x, own_y, own_vx, own_vy,
            opp_x, opp_y, opp_vx, opp_vy,
            own_hp, opp_hp, own_spirit, opp_spirit,
            own_gauge, opp_gauge, own_hand, opp_hand,
            dx, weather_id, weather_counter,
            own_action, opp_action, own_facing,
            bl_nearest, bl_count, macro_id):
        self.rows.append([
            (own_x or 0) / 2000.0, (own_y or 0) / 500.0,
            (own_vx or 0) / 8.0, (own_vy or 0) / 8.0,
            (opp_x or 0) / 2000.0, (opp_y or 0) / 500.0,
            (opp_vx or 0) / 8.0, (opp_vy or 0) / 8.0,
            (own_hp or 0) / 10000.0, (opp_hp or 0) / 10000.0,
            (own_spirit or 0) / 1000.0, (opp_spirit or 0) / 1000.0,
            (own_gauge or 0) / 500.0, (opp_gauge or 0) / 500.0,
            (own_hand or 0) / 5.0, (opp_hand or 0) / 5.0,
            (dx or 0) / 1000.0,
            (weather_id or 0) / 22.0, (weather_counter or 0) / 1200.0,
            (own_action or 0) / 1000.0, (opp_action or 0) / 1000.0,
            1.0 if (own_facing or 0) > 0 else 0.0,
            (bl_nearest if bl_nearest is not None else 1000) / 500.0,
            (bl_count or 0) / 10.0,
            float(macro_id),
        ])
        if len(self.rows) > 50000:
            self.rows = self.rows[-50000:]

    def save(self):
        self._ensure_loaded()
        if not self.rows:
            return
        arr = np.asarray(self.rows, dtype=np.float32)
        np.savez(self.path, T=arr)
