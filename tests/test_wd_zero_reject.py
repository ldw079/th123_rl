# -*- coding: utf-8 -*-
"""H-1(2026-10-19) 行为测试: 族 CPU `0.00` 拒收守卫 + 连续2次恢复门控 + wd 第3字段.

事故: 夜内 fleet_heartbeat.wd 出现 8 次 0.00(13:05/17:35/20:32/…), 当时主臂
7py+3游戏+对照臂全在(真实负载非0)。根因=fleet_supervisor.cpu_load_pct 在
Δ族累计CPU≤0(CIM偶发旧值/抖动)时 clamp 成 0.0, 且 CpuWatchdog.sample 只拒收
None/负值 → 0.0 入窗, 单次拉低 6 窗均值 ~6pp, 可稀释 75% 红线。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
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
    return {'ProcessId': pid, 'ParentProcessId': ppid,
            'KernelModeTime': int(cpu_s * 1e7), 'UserModeTime': 0}


def _ps(cpu_s):
    """单行 JSON: root(自身 pid=fs.os.getpid())+ 1 child, 累计CPU=cpu_s。"""
    root = fs.os.getpid()
    return json.dumps([_row(root, 1, cpu_s), _row(root + 1, root, 0.0)])


def _reset():
    fs._WD_CPU_LAST['ts'] = fs._WD_CPU_LAST['cpu'] = None
    fs._WD_CPU_LAST['pct'] = None
    fs._WD_ZERO_REJECT = 0


# ---- A) 正常两拍 → 第三拍 ΔCPU=0 → None 哨兵 + 计数, 不产 0.0 ----
_reset()
p1 = fs.cpu_load_pct(now=100.0, ps_out=_ps(100.0), cores=18,
                     root_pid=None)
p2 = fs.cpu_load_pct(now=130.0, ps_out=_ps(130.0), cores=18)
ck(p1 is None, 'A1 首拍无 Δt → None(不产 0.0)')
ck(p2 is not None and p2 > 0, 'A2 正常拍产 >0 百分比')
p3 = fs.cpu_load_pct(now=160.0, ps_out=_ps(130.0), cores=18)  # ΔCPU=0
ck(p3 is None, 'A3 Δ族CPU=0 → None 哨兵(拒收, 不再产 0.0)')
ck(fs._WD_ZERO_REJECT == 1, 'A4 拒收计数 +1')

# ---- B) 负 Δ(进程退出/旧值) 同样拒收 ----
p4 = fs.cpu_load_pct(now=190.0, ps_out=_ps(120.0), cores=18)  # ΔCPU<0
ck(p4 is None and fs._WD_ZERO_REJECT == 2,
   'B1 Δ族CPU<0(进程退出/CIM旧值) 拒收 + 计数')

# ---- C) CpuWatchdog: 拒收后需连续 2 次正常采样才恢复入窗 ----
wd = fs.CpuWatchdog(window=6)
for i in range(6):
    wd.sample(30.0, now=float(i))
ck(wd.avg is not None, 'C1 6 正常拍 → 均值成立(基线)')
_len0 = len(wd.win)
wd.sample(None, now=10.0)          # 拒收哨兵
ck(len(wd.win) == _len0 and wd._recover_need == 2,
   'C2 拒收拍不入窗且置 recover_need=2')
wd.sample(30.0, now=11.0)          # 第 1 次正常: 仅递减, 不入窗
ck(len(wd.win) == _len0 and wd._recover_need == 1,
   'C3 拒收后第 1 次正常被门控(不入窗, need→1)')
wd.sample(30.0, now=12.0)          # 第 2 次正常: 递减到 0, 仍不入窗
ck(len(wd.win) == _len0 and wd._recover_need == 0,
   'C4 拒收后第 2 次正常仍被门控(不入窗, need→0)')
wd.sample(30.0, now=13.0)          # 第 3 次正常: 恢复入窗
ck(len(wd.win) == _len0 and wd.avg is not None,
   'C5 第 3 次正常才恢复入窗并算均值')

# ---- D) wd sidecar 第3字段 + 旧读者兼容 + 拒收 append 日志 ----
tmpd = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.wd_test_tmp')
os.makedirs(tmpd, exist_ok=True)
old_wd = fs.WD_STATUS
old_store = fs.STORE
try:
    fs.WD_STATUS = os.path.join(tmpd, 'fleet_heartbeat.wd')
    fs.STORE = tmpd
    fs.write_watchdog_status(33.25, now=1790000000.0, n_rej=2)
    line = io.open(fs.WD_STATUS, encoding='utf8').read().strip()
    parts = line.split()
    ck(len(parts) == 3 and parts[1] == '33.25' and parts[2] == '2',
       'D1 sidecar 3 字段: ts pct n_rej')
    ck(parts[1] == '33.25', 'D2 旧读者 split()[1] 仍是百分比')
    fs.write_watchdog_status(None, now=1790000030.0, n_rej=3, rejected=True)
    parts = io.open(fs.WD_STATUS, encoding='utf8').read().split()
    ck(parts[1] == '-' and parts[2] == '3', 'D3 拒收拍写 "-" + 计数')
    rj = io.open(os.path.join(tmpd, 'watchdog_rejects.log'),
                 encoding='utf8').read()
    ck('rejected n_rej=3' in rj, 'D4 拒收 append 审计日志')
finally:
    fs.WD_STATUS = old_wd
    fs.STORE = old_store
    import shutil
    shutil.rmtree(tmpd, ignore_errors=True)

print('\n==== H-1 wd 0.00 拒收守卫: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
