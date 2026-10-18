# -*- coding: utf-8 -*-
"""LE-0a 对照臂连续性: 终止路径豁免静态测试(R202 事故回归).

2026-10-18 16:27-16:38 实弹: `fleet_supervisor.reap_orphans()` 启动时按
"父进程已死"回收 `actor_worker|learner_hub|exploiter` python, 但**无**
`th123_rl_control` 豁免 → 主臂重启时把 LE-0a 对照臂(手工 launcher 启动,
父进程已退出=孤儿)连树杀掉, 对照臂中断 639s / 游戏 21080 缺失 ~8.5min。

本测试**只做静态扫描**(不执行任何 kill):
  1) `fleet_supervisor.py` 中所有 "Get-CimInstance Win32_Process" 查询,
     若其选择了训练 python(`actor_worker|learner_hub|exploiter`), 则同一查询
     片段必须含 `th123_rl_control` 豁免;
  2) `tools/train_start.py._cleanup_ps_cmd`(pre_flight/stop 共用) 必须同时含
     `taskkill` 与 `th123_rl_control` 豁免;
  3) 豁免必须是"负匹配"语义(`-notmatch 'th123_rl_control'`), 不是仅注释提及。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf8')

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    if cond:
        print('  PASS  %s' % name)
    else:
        BAD += 1
        print('  FAIL  %s' % name)


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8').read()


sup = _read('fleet_supervisor.py')
ts = _read('tools/train_start.py')

# ---- 1) supervisor: 每个"选训练 python"的 WMI 查询都必须带豁免 ----
_seen = 0
for m in re.finditer(r'Get-CimInstance Win32_Process', sup):
    seg = sup[max(0, m.start() - 500):m.start() + 1500]
    if not re.search(r'actor_worker\|learner_hub\|exploiter', seg):
        continue
    _seen += 1
    _ln = sup[:m.start()].count('\n') + 1
    ck('th123_rl_control' in seg,
       'supervisor 查询@L%d 含对照臂豁免(th123_rl_control)' % _ln)
ck(_seen >= 1, 'supervisor 至少发现 1 处训练python查询(实际%d)' % _seen)

# 豁免必须是负匹配语义(排除), 不是正向包含
ck("-notmatch 'th123_rl_control'" in sup,
   "supervisor 豁免为 -notmatch 负匹配语义")

# ---- 2) train_start._cleanup_ps_cmd: taskkill 与豁免同函数 ----
_i = ts.find('def _cleanup_ps_cmd')
ck(_i >= 0, 'train_start 存在 _cleanup_ps_cmd(前置清理/停机共用)')
_seg = ts[_i:_i + 3500] if _i >= 0 else ''
ck('taskkill' in _seg, 'cleanup 函数体含 taskkill')
ck('th123_rl_control' in _seg, 'cleanup 函数体含对照臂豁免')
ck("-notmatch 'th123_rl_control'" in _seg,
   'cleanup 豁免为 -notmatch 负匹配语义')

# ---- 3) 游戏侧豁免: 清理按父进程判(注释/实现锚) ----
ck('ParentProcessId' in sup and 'th123_rl_control' in sup,
   '孤儿回收保留 ParentProcessId 判定 + 对照臂豁免')

print('\n==== LE-0a 对照臂豁免静态测试: %d PASS / %d FAIL ===='
      % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
