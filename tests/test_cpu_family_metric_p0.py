# -*- coding: utf-8 -*-
"""P0-3(从零#5)行为测试: CPU看门狗口径必须是"训练族进程树", 不是整机负载。

审计实证(2026-10-17): 整机 100% 时 fleet 全家(3 learner + 3 actor + 监督器
+ 3 游戏)实测仅 ≈17% — 其余是旁路(ZCode 会话/变异 sweep/BC 重建)。原实现
取 Win32_Processor.LoadPercentage, 于是:
  ① 旁路负载被算作训练负载 → 看门狗误杀 actor;
  ② 恢复线(<65% 连续两满窗)在旁路不退时永不满足 → 10-14 震荡 32min/8 次。
同批还顺带证明"树口径"能自动豁免对照臂(独立 worktree/独立树)。

本测试钉死五件事:
1. 树内(自身+子进程+孙进程=游戏)累计 CPU 计入;
2. **树外**(兄弟树=对照臂/旁路)一律不计入 —— 本次修复的核心语义;
3. ConvertTo-Json 单元素返回**对象**而非数组时必须归一(真实 PowerShell 行为);
4. 采样失败 = None 哨兵(看门狗拒收), 不是 0(否则假均值会触发恢复震荡);
5. 比率 = Δ族CPU /(Δ墙钟 × 逻辑核数) ×100, 负 Δ 与越界一律 clamp。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

import fleet_supervisor as fs   # noqa: E402

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


def _row(pid, ppid, cpu_s):
    """构造一条 Win32_Process 采样行(CPU 用 100ns 单位, 与真实 CIM 一致)。"""
    return {'ProcessId': pid, 'ParentProcessId': ppid,
            'KernelModeTime': int(cpu_s * 1e7),
            'UserModeTime': 0}


# 进程树:
#   100 监督器 ── 200 actor ── 300 th123.exe(游戏)
#   400 另一棵树的 actor(对照臂) ── 500 对照臂游戏
#   600 旁路 python(变异 sweep), 父进程不在表内
_TABLE = [
    _row(100, 1, 5.0),      # supervisor 自身
    _row(200, 100, 7.0),    # actor
    _row(300, 200, 11.0),   # 游戏(孙进程)
    _row(400, 9000, 60.0),  # 对照臂 actor(树外)
    _row(500, 400, 50.0),   # 对照臂游戏(树外)
    _row(600, 7777, 30.0),  # 旁路 sweep(树外)
]
_JSON = json.dumps(_TABLE, ensure_ascii=False)

# ── 1. 树内累计 ──
_total = fs.family_cpu_seconds(root_pid=100, ps_out=_JSON)
ck(_total is not None and abs(_total - 23.0) < 1e-6,
   '族CPU=树内累计(自身5+子7+孙11=23s): 实测 %r' % (_total,))

# ── 2. 树外不计入(核心语义: 旁路/对照臂不得算进训练负载) ──
ck(abs(_total - 23.0) < 1e-6 and _total < 140.0,
   '树外(兄弟树/旁路)不计入 — 全表累计是140s, 族口径必须是23s')

# ── 3. 单元素对象归一(ConvertTo-Json 真实怪癖) ──
_one = fs.family_cpu_seconds(root_pid=100, ps_out=json.dumps(_row(100, 1, 4.0)))
ck(_one is not None and abs(_one - 4.0) < 1e-6,
   '单元素JSON对象(非数组)归一: 实测 %r' % (_one,))

# ── 4. 失败=哨兵None(不是0) ──
ck(fs.family_cpu_seconds(root_pid=100, ps_out='{坏json') is None,
   '坏JSON → None哨兵(家族CPU不可当0用)')
ck(fs.family_cpu_seconds(root_pid=100, ps_out='') == 0.0,
   '空表 → 0.0(进程都没了与查询失败必须区分)')

# ── 5. 比率口径 + clamp ──
fs._WD_CPU_LAST.update({'ts': None, 'cpu': None, 'pct': None})
_r1 = fs.cpu_load_pct(now=1000.0, ps_out=json.dumps([_row(100, 1, 10.0)]),
                      cores=4, root_pid=100)
ck(_r1 is None, '首次采样无Δt → None(看门狗拒收, 不产生假均值): %r' % (_r1,))
_r2 = fs.cpu_load_pct(now=1002.0, ps_out=json.dumps([_row(100, 1, 14.0)]),
                      cores=4, root_pid=100)
ck(_r2 is not None and abs(_r2 - 50.0) < 1e-6,
   '比率=ΔCPU/(Δ墙钟×核数)×100 → 4s/(2s×4核)=50%%: 实测 %r' % (_r2,))
_r3 = fs.cpu_load_pct(now=1004.0, ps_out=json.dumps([_row(100, 1, 12.0)]),
                      cores=4, root_pid=100)
ck(_r3 == 0.0, '负Δ(进程退出) clamp 到 0(不得入负数窗口): %r' % (_r3,))
_r4 = fs.cpu_load_pct(now=1006.0, ps_out=json.dumps([_row(100, 1, 1000.0)]),
                      cores=1, root_pid=100)
ck(_r4 == 100.0, '越界 clamp 到 100: %r' % (_r4,))

# ── 6. 失败采样不污染上次时点(否则下次Δt虚高) ──
_ts_before = fs._WD_CPU_LAST['ts']
ck(fs.cpu_load_pct(now=1008.0, ps_out='{坏json', cores=4,
                   root_pid=100) is None
   and fs._WD_CPU_LAST['ts'] == _ts_before,
   '查询失败不改写采样时点(防下次Δt虚高→假低值)')

# ── 7. 整机口径不得复活(与门禁断言同义, 行为测试里再钉一次) ──
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'fleet_supervisor.py'),
    encoding='utf8').read()
ck('Get-CimInstance Win32_Processor' not in _src,
   '整机处理器利用率查询已退役 — 旁路负载不可冒充训练负载')

print()
print('==== %d PASS / %d FAIL ====' % (N - BAD, BAD))
sys.exit(1 if BAD else 0)
