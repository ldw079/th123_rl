# -*- coding: utf-8 -*-
"""A1/A2(CPU-H P-B/P-C) 行为测试: wd 5字段/整机/旁路口径/L3 告警/工具闸门接入."""
import io
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.stdout.reconfigure(encoding='utf8')

import fleet_supervisor as fs  # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    print('  PASS  %s' % name if cond else '  FAIL  %s' % name)
    if not cond:
        BAD += 1


td = tempfile.mkdtemp(prefix='l0_')
fs.WD_STATUS = os.path.join(td, 'fleet_heartbeat.wd')
fs.MACHINE_ALERT = os.path.join(td, 'fleet_heartbeat.machine_alert')
fs.STORE = td

# ---- 1. wd 5 字段 + 旧读者兼容 ----
fs.write_watchdog_status(33.3, now=1790000000.0, n_rej=2,
                         machine=77.7, aux=5.5)
parts = io.open(fs.WD_STATUS, encoding='utf8').read().split()
ck(len(parts) == 5, 'wd 5 字段 (ts family n_rej machine aux)')
ck(parts[1] == '33.30' and parts[3] == '77.70' and parts[4] == '5.50',
   'wd 旧读者 split()[1]=族; 新字段 machine/aux 正确')
fs.write_watchdog_status(None, now=1790000030.0, n_rej=3,
                         machine=None, aux=None)
parts = io.open(fs.WD_STATUS, encoding='utf8').read().split()
ck(parts[1] == '-' and parts[2] == '3' and parts[3] == '-'
   and parts[4] == '-', 'wd 失败哨兵 None → "-"')

# ---- 2. 整机口径 ----
m1 = fs.machine_cpu_pct()
time.sleep(0.35)
m2 = fs.machine_cpu_pct()
ck(m1 is None, '整机首拍 None(无Δ)')
ck(m2 is not None and 0.0 <= m2 <= 100.0, '整机第二拍 0-100 (%r)' % (m2,))

# ---- 3. 旁路口径: 排除族与对照臂 ----
rows = [(100, 1, 100.0, 'python.exe actor_worker'),
        (101, 100, 50.0, 'python.exe learner_hub'),
        (200, 1, 900.0, 'python.exe th123_rl_control actor_worker'),
        (300, 1, 200.0, 'python.exe zcode_helper')]
fam = fs._family_pids_from_rows(rows, 100)
ck(100 in fam and 101 in fam and 200 not in fam and 300 not in fam,
   '族树识别(子进程在内, 对照臂/旁路在外)')
fs._AUX_LAST['ts'] = 1000.0
fs._AUX_LAST['cpu'] = 0.0
a = fs.aux_cpu_pct(now=1001.0, rows=rows)   # Δ=(0+0)=0 → 只有300? 200被排除
ck(a is not None and a >= 0.0, 'aux 计算 0-100 (%r)' % (a,))
fs._AUX_LAST['ts'] = 2000.0
fs._AUX_LAST['cpu'] = 0.0
rows2 = [(300, 1, 18.0, 'python.exe zcode_helper')]
a2 = fs.aux_cpu_pct(now=2002.0, rows=rows2)
ck(a2 is not None and abs(a2 - (18.0 / (2.0 * fs._LOGICAL_CORES) * 100.0)) < 1e-6,
   'aux = Δ旁路CPU/(Δ墙钟×核数) (%r)' % (a2,))

# ---- 4. L3: 阈值/告警/不杀 fleet ----
fs._L3_STATE.update({'m_hi': 0, 'm_crit': 0, 'last_alert': 0.0})
ck(fs.l3_check(85.5, 50.0) is None and fs.l3_check(85.5, 50.0) is None,
   'machine>85 前两窗不告警')
ck(fs.l3_check(85.5, 50.0) == 'alert', 'machine>85 连续3窗 → alert')
ck(os.path.exists(fs.MACHINE_ALERT), 'machine_alert 文件已写')
al = io.open(fs.MACHINE_ALERT, encoding='utf8').read()
ck('machine>85' in al and '不杀' not in al, 'alert 内容含原因')
fs._L3_STATE.update({'m_hi': 0, 'm_crit': 0, 'last_alert': 0.0})
fs.l3_check(96.0, 40.0)
ck(fs.l3_check(96.0, 40.0) == 'critical', 'machine>95 连续2窗 → critical')
src = io.open(os.path.join(ROOT, 'fleet_supervisor.py'), encoding='utf8').read()
_l3 = src[src.find('def l3_check('):]
_l3 = _l3[:_l3.find('\ndef ')]
ck('_kill_tree' not in _l3 and 'actors' not in _l3,
   'L3 不杀 fleet(无 _kill_tree/actors 操作)')

# ---- 5. dashboard 三口径 ----
import status_dashboard as dash  # noqa: E402
dash.STORE = td
txt, ok = dash.get_watchdog_status()
ck('族CPU' in txt and '整机' in txt and '旁路' in txt,
   'dashboard 三口径显示: %s' % txt[:60])

# ---- 6. 工具闸门接入(P-C) ----
for rel, kind in (('bc_build.py', 'bc_build'),
                  ('tools/eval_matrix.py', 'eval_matrix'),
                  ('tools/audit_all.py', 'audit_all')):
    s = io.open(os.path.join(ROOT, rel), encoding='utf8').read()
    ck('guard_tool(' in s and ("'%s'" % kind) in s,
       '%s 接入 load_gate.guard_tool' % rel)

print('\n==== A1/A2 L0/L3/P-C: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
