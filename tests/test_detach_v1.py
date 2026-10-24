# -*- coding: utf-8 -*-
"""C15(task-47): train_detach --allow-batch 透传 + 启动校验 + WMI 回退 (纯逻辑注入)."""
import os
import sys
import tempfile

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, 'tools'))
os.chdir(WT)
FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


import train_detach as D  # noqa: E402

print('== detach v1 ==')
base = {'TH123_BATCH_K': '2', 'TH123_BATCH_MIN_GAMES': '2',
        'TH123_BATCH_WAIT_MAX': '120', 'TH123_BUFFER': '1',
        'TH123_BCW_MIN': '0.05'}
k = D.filter_batch_env(base, True)
chk('allow_batch=1 保留 BATCH_*',
    k.get('TH123_BATCH_K') == '2' and k.get('TH123_BATCH_WAIT_MAX') == '120')
k2 = D.filter_batch_env(base, False)
chk('allow_batch=0 剔除 BATCH_*',
    all('TH123_BATCH_' not in x for x in k2) and k2.get('TH123_BUFFER') == '1')
chk('非 BATCH env 不受影响', k2.get('TH123_BCW_MIN') == '0.05')

# verify_started: 日志 marker 命中
tmp = tempfile.mkdtemp(prefix='dt47_')
lp = os.path.join(tmp, 'main.log')
open(lp, 'w', encoding='utf8').write('xx\n全部启动 — 监督模式\n')
chk('启动校验: 日志"监督模式"命中', D.verify_started(1.0, log_path=lp))

# verify_started: 进程存在(注入 subprocess.run)
class _R:
    def __init__(self, out):
        self.returncode = 0
        self.stdout = out
        self.stderr = ''


_orig_run = D.subprocess.run


def fake_proc_run(cmd, *a, **kw):
    return _R('1\n')


D.subprocess.run = fake_proc_run
try:
    chk('启动校验: 进程存在命中', D.verify_started(1.0, log_path=None))
finally:
    D.subprocess.run = _orig_run

# launch_wmi: ret=0 / ret=5
D.subprocess.run = lambda cmd, *a, **kw: _R('ret=0\n')
try:
    ok, det = D.launch_wmi(r'D:\temp\x.bat')
    chk('WMI 回退 ret=0 判定成功', ok)
finally:
    D.subprocess.run = _orig_run
D.subprocess.run = lambda cmd, *a, **kw: _R('ret=5\n')
try:
    ok2, _ = D.launch_wmi(r'D:\temp\x.bat')
    chk('WMI 回退 ret=5 判定失败', not ok2)
finally:
    D.subprocess.run = _orig_run

# launch: schtasks Queued → WMI 回退 → 校验通过
calls = {'v': 0}


def fake_verify(timeout_s=60.0, log_path=None):
    calls['v'] += 1
    return calls['v'] >= 2


D.write_launcher_bat = lambda *a, **k2: 'x.bat'
D.launch_schtasks = lambda bat, *a, **k2: (True, 'fake')
D.verify_started = fake_verify
D.launch_wmi = lambda bat: (True, 'wmi-ok')
try:
    res = D.launch(['py'], '.', {}, os.path.join(tmp, 'm.log'),
                   dry=False, via='schtasks', verify_timeout=1)
    chk('schtasks Queued → WMI 回退成功', res.get('mode') == 'schtasks+wmi')
finally:
    import importlib
    importlib.reload(D)

# CLI: --allow-batch 出现在 --help
import subprocess as _sp
h = _sp.run([sys.executable, '-X', 'utf8', 'tools/train_detach.py', '--help'],
            capture_output=True, text=True, encoding='utf-8', errors='replace')
chk('CLI 含 --allow-batch/--verify-timeout',
    '--allow-batch' in (h.stdout or '') and
    '--verify-timeout' in (h.stdout or ''))
src = open(os.path.join(WT, 'tools/train_detach.py'), encoding='utf8').read()
chk('源码含 WMI 回退/启动校验', 'launch_wmi' in src and
    'verify_started' in src and 'filter_batch_env' in src)
print('==== detach v1: %d PASS / %d FAIL ===='
      % (11 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
