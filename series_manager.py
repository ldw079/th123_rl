# -*- coding: utf-8 -*-
"""E阶段1(系列预测方案§3, BO15修订): SeriesManager — 系列赛环境层.

BO15语义(用户裁定2026-10-06修订): 同一对手连续最多15场完整对局,
先到8胜封顶 — 非旧稿"5场BO3"。

职责(方案§3.1):
  - 轮换发令: 系列内(未到series_win且未满series_len)→ 抑制对手轮换
    + 对手画像不重置(跨场携带); 系列结束(8胜或15场)→ 正常轮换+重置;
  - legacy模式(series_len=0): 完全退役, train_tm走原(ep+1)%5周期,
    逐位不变(归因隔离: A/B期间不部署系列模式 — 方案§7前置依赖)。

接线点: train_tm.train()的_rotate_opp判定与_run_episode的reset_match
调用均以此处决定为准(仅series模式生效); episode meta携带series_id/
match_in_series/opp_tag(加法式字段, 不动EP_SCHEMA — 布局未变, 双向
兼容: 老读者忽略新字段, 新读者缺字段回退 — position_from_meta已就位)。
"""
from __future__ import annotations

SERIES_LEN_DEFAULT = 15   # BO15场数上限
SERIES_WIN_DEFAULT = 8    # 先到8胜封顶


class SeriesManager:
    """一个训练器实例持一个(对手=当前锁定的池快照角色)."""

    def __init__(self, series_len=SERIES_LEN_DEFAULT,
                 series_win=SERIES_WIN_DEFAULT):
        assert series_len >= 1 and 1 <= series_win <= series_len
        self.series_len = series_len
        self.series_win = series_win
        self.series_id = 0
        self.match_in_series = 0     # 已完成场数
        self.my_wins = 0
        self.opp_wins = 0

    # ---- 查询 ----
    @property
    def in_series(self):
        """系列是否继续(未封顶未满场)."""
        return (self.my_wins < self.series_win
                and self.opp_wins < self.series_win
                and self.match_in_series < self.series_len)

    @property
    def match_number_next(self):
        """下一场是系列内第几场(1起)."""
        return self.match_in_series + 1

    def should_reset_profiles(self):
        """下一场是否重置双方画像(= 系列首场)."""
        return self.match_in_series == 0

    # ---- 事件 ----
    def on_match_end(self, my_win):
        """场结束: 记分; 返回 series_over(bool)."""
        self.match_in_series += 1
        if my_win:
            self.my_wins += 1
        else:
            self.opp_wins += 1
        if not self.in_series:
            over = True
            self._advance_series()
            return over
        return False

    def _advance_series(self):
        self.series_id += 1
        self.match_in_series = 0
        self.my_wins = 0
        self.opp_wins = 0

    def meta_fields(self, opp_tag):
        """episode meta附加字段(E阶段1, 加法式)."""
        return {'series_id': self.series_id,
                'match_in_series': self.match_number_next,
                'opp_tag': opp_tag}
