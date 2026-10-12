# -*- coding: utf-8 -*-
"""R75(2026-10-12全灭事故): CPU红线降容/恢复策略 — 行为断言.

事故形态回放: 16:51/17:02/17:10三actor接连被降容删除, 之后无任何恢复
路径, 车队空转55min(learner无数据)。修正后语义:
  1. 高CPU满窗 → kill决策, 降容后窗口重置(防连环杀);
  2. 暂停簿记: pop_resumable未满min_suspend不给恢复(防抖);
  3. 低CPU满窗 → resume决策一次只给一个(爬坡恢复);
  4. 今日事故序列: 三连杀(窗口重置间隔)后持续低CPU → 三个全部可恢复;
  5. 滞后带: 均值在[REENTER, RED_LINE]之间 → 无决策(不抖动);
  6. 监督循环源码锚定: 暂停路径存在suspend调用+恢复路径spawn(防回归
     到"del后不管")。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fleet_supervisor import (CpuWatchdog, CPU_RED_LINE, CPU_REENTER,
                              CPU_WINDOW, SUSPEND_MIN_S)

FAILS = []


def check(name, cond, detail=''):
    print('%-56s %s %s' % (name, 'PASS' if cond else 'FAIL',
                           detail if not cond else ''))
    if not cond:
        FAILS.append(name)


wd = CpuWatchdog()

# ---- 1. 高CPU满窗→kill, 窗口重置 ----
t = 0.0
dec = None
for i in range(CPU_WINDOW):
    dec, avg = wd.sample(90.0, t)
check('高CPU满窗→kill决策(均值90)', dec == 'kill' and avg == 90.0)
check('降容判定后窗口重置(防连环杀)', wd.win == [])
dec2, _ = wd.sample(95.0, t)
check('窗口未满不再连环杀', dec2 is None)

# ---- 2. 暂停簿记与防抖 ----
wd.suspend(('reimu', 0), t)
check('未满min_suspend不给恢复',
      wd.pop_resumable(t + SUSPEND_MIN_S - 1) is None)
check('满min_suspend给最早暂停的',
      wd.pop_resumable(t + SUSPEND_MIN_S) == ('reimu', 0))
check('恢复后簿记清空', wd.suspended_at == {})

# ---- 3. 低CPU满窗→resume(一次一个) ----
wd = CpuWatchdog()
for i in range(CPU_WINDOW):
    dec, avg = wd.sample(40.0, t + i)
check('低CPU满窗→resume决策(均值40)', dec == 'resume' and avg == 40.0)

# ---- 4. 今日事故序列全回放 ----
wd = CpuWatchdog()
now = 0.0
suspended = []
actors = [('reimu', 0), ('marisa', 1), ('suika', 2)]
# 三波高CPU(每波之间窗口被kill重置 → 杀完需要重新满窗 — 与今日
# 16:51/17:02/17:10节奏同构), 全部actor暂停
while actors:
    dec, _ = wd.sample(90.0, now)
    now += 30.0
    if dec == 'kill':
        _k = sorted(actors)[-1]
        actors.remove(_k)
        wd.suspend(_k, now)
        # 窗口重置后不再连杀: 下一kill需重新满窗
        for _ in range(CPU_WINDOW):
            wd.sample(90.0, now)
            now += 30.0
check('事故序列: 三actor全部暂停', len(wd.suspended_at) == 3 and not actors)
# 持续低CPU(根因消除, 如今日杀掉超预算剥削者) → 三波恢复, 每波满窗一个
resumed = []
for wave in range(3):
    dec = None
    while dec != 'resume':
        dec, _ = wd.sample(40.0, now)
        now += 30.0
    _k = wd.pop_resumable(now)
    if _k is not None:
        resumed.append(_k)
check('低CPU后全部可恢复(一次一个)',
      len(resumed) == 3 and len(wd.suspended_at) == 0,
      'resumed=%s' % resumed)

# ---- 5. 滞滞带: 65<=avg<=75 无决策 ----
wd = CpuWatchdog()
dec, avg = None, None
for i in range(CPU_WINDOW):
    dec, avg = wd.sample(70.0, t)
check('滞后带[65,75]无决策(不抖动)', dec is None and avg == 70.0)

# ---- 6. 监督循环源码锚定(R75接线不可静默回退) ----
src = open(os.path.join(ROOT, 'fleet_supervisor.py'),
           encoding='utf8').read()
check('暂停路径: suspend(调用在位)', '_wd.suspend(_k, time.time())' in src)
check('恢复路径: pop_resumable+_spawn_actor(调用在位)',
      '_wd.pop_resumable(time.time())' in src and
      '_spawn_actor(ch, aid, fleet_port(aid),' in src)
check('全灭告警行在位', '[告警] 车队actor全灭' in src)
check('常量: 回入场线65<红线75', CPU_REENTER < CPU_RED_LINE)

print()
if FAILS:
    print('FAIL(%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('ALL PASS (14)')
