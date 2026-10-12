# -*- coding: utf-8 -*-
"""E阶段1(系列方案§3, BO15=15场先到8胜) 配对测试: SeriesManager.

覆盖:
  1. BO15语义: 8胜早停(未满15场)/15场封顶(无8胜)
  2. 系列边界: 结束后series_id推进/match归零/should_reset_profiles翻转
  3. 跨场携带: 系列内should_reset_profiles()=False(第2场起)
  4. meta字段: match_in_series从1起/opp_tag回填
  5. legacy兼容: _series_mgr=None时train_tm路径不触系列逻辑(构造级)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from series_manager import SeriesManager

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def main():
    # 1. 8胜早停
    sm = SeriesManager(series_len=15, series_win=8)
    ok(sm.should_reset_profiles() and sm.match_number_next == 1,
       '系列首场: 画像重置+第1场')
    overs = [sm.on_match_end(True) for _ in range(7)]
    ok(not any(overs) and sm.my_wins == 7 and sm.match_in_series == 7,
       '7连胜未封顶(系列继续)')
    over = sm.on_match_end(True)          # 第8胜
    ok(over and sm.series_id == 1 and sm.match_in_series == 0,
       '第8胜封顶: series_over + 新系列(id=1, 归零)')
    ok(sm.should_reset_profiles(), '新系列首场画像重置')

    # 2. 场数封顶(BO15里15场封顶必伴第8胜 — 纯封顶用len=5/win=4构造:
    #    2-2后第5场2-3, 无4胜仍结束)
    sm2 = SeriesManager(5, 4)
    for _ in range(2):
        sm2.on_match_end(True)
    for _ in range(2):
        sm2.on_match_end(False)
    ok(sm2.in_series and sm2.match_in_series == 4, '2-2平局态系列继续')
    last = sm2.on_match_end(False)         # 第5场 2-3
    ok(last and sm2.series_id == 1 and sm2.my_wins == 0,
       '场数封顶(2-3无4胜): series_over推进+归零')
    # BO15语义补充: 7-7后第15场必产生8-7(封顶与第8胜同拍)
    sm2b = SeriesManager(15, 8)
    for _ in range(7):
        sm2b.on_match_end(True)
    for _ in range(7):
        sm2b.on_match_end(False)
    over15 = sm2b.on_match_end(True)
    ok(over15 and sm2b.series_id == 1,
       'BO15决胜场(7-7→8-7): 封顶与第8胜同拍')

    # 3. 跨场携带(第2场起不重置)
    sm3 = SeriesManager(15, 8)
    sm3.on_match_end(True)
    ok(not sm3.should_reset_profiles() and sm3.match_number_next == 2,
       '系列第2场: 画像携带(不重置)')

    # 4. meta字段
    mf = sm3.meta_fields('suika@seed_20261011')
    ok(mf == {'series_id': 0, 'match_in_series': 2,
              'opp_tag': 'suika@seed_20261011'},
       'meta字段(series_id/match_in_series从1起/opp_tag)')

    # 5. legacy兼容: train_tm默认_series_mgr=None(构造级 — 全量行为
    #    回归由门禁既有575断言+行为测试承担, 此处钉构造默认)
    import train_tm
    import inspect
    src = inspect.getsource(train_tm.TMTrainer.__init__)
    ok('self._series_mgr = None' in src,
       'legacy默认: _series_mgr=None(A/B期间不部署系列模式)')

    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
