# -*- coding: utf-8 -*-
"""开机/登录后自动恢复训练（**opt-in；用户裁定 2026-10-26 10:06 不启用**：不安装计划任务；保留脚本仅备未来显式 opt-in）.

规则（Lead 2026-10-26 10:03）:
- 仅当 `D:\temp\th123_models\train_resume_on_boot` 标志存在才恢复（用户主动关机不自动拉起）；
- 已有 supervisor 在跑→跳过（防重复）；维护锁有效→跳过（窗进行中）；
- WMI 唯一入口（main bat + control bat + watcher）；记录到 fleet_heartbeat.recovery；
- 失败告警写 fleet_alert。

用法:
  python tools/boot_resume.py [--check]   # --check 只判定不动作
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

STORE = r'D:\temp\th123_models'
FLAG = os.path.join(STORE, 'train_resume_on_boot')
HB = os.path.join(STORE, 'fleet_heartbeat')
ALERT = HB + '.fleet_alert'
BAT = r'D:\temp\train_batch_launch.bat'
CTL_BAT = r'D:\temp\launch_control_actor.bat'
CTL_LEARNER_BAT = r'D:\temp\launch_control_learner.bat'


def _ps(script):
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', enc],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=120)
    return (r.stdout or '').strip(), (r.stderr or '').strip()


def supervisor_running():
    out, _ = _ps("Get-CimInstance Win32_Process | ? {$_.Name -eq "
                 "'python.exe' -and $_.CommandLine -match "
                 "'fleet_supervisor'} | % {$_.ProcessId}")
    return bool(out.strip())


def lock_active():
    try:
        import fleet_lock
        return fleet_lock.status().get('active', False)
    except Exception:
        return False


def should_resume(flag_exists, sup_running, lock_on):
    """纯决策: 返回 (bool, reason)."""
    if not flag_exists:
        return False, 'flag_absent'
    if sup_running:
        return False, 'supervisor_already_running'
    if lock_on:
        return False, 'maintenance_lock'
    return True, 'resume'


def wmi_create(cmd):
    out, err = _ps("$r=Invoke-CimMethod -ClassName Win32_Process "
                   "-MethodName Create -Arguments @{CommandLine='%s'}; "
                   "Write-Output ('ret='+$r.ReturnValue+' pid='+$r.ProcessId)"
                   % cmd)
    return out


def write_recovery(entry):
    try:
        os.makedirs(STORE, exist_ok=True)
        io = open(HB + '.recovery', 'w', encoding='utf-8')
        io.write(json.dumps(entry, ensure_ascii=False))
        io.close()
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    ok, reason = should_resume(os.path.exists(FLAG), supervisor_running(),
                               lock_active())
    print('[boot_resume]', reason)
    if a.check or not ok:
        return 0 if not a.check else (0 if ok else 1)
    outs = {}
    outs['main'] = wmi_create('cmd.exe /c ' + BAT)
    if os.path.exists(CTL_BAT):
        outs['control_actor'] = wmi_create('cmd.exe /c ' + CTL_BAT)
    if os.path.exists(CTL_LEARNER_BAT):
        outs['control_learner'] = wmi_create('cmd.exe /c ' + CTL_LEARNER_BAT)
    wcmd = ('cmd.exe /c D:\\temp\\pyenv\\python.exe -X utf8 -u '
            '"C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\tools\\'
            'fleet_health.py" --loop 60 --auto-recover >> '
            'D:\\temp\\fleet_health_watch.log 2>&1')
    outs['watcher'] = wmi_create(wcmd)
    write_recovery({'ts': time.time(), 'code': 'boot_resume',
                    'reason': reason, 'outs': outs})
    print('[boot_resume] launched', json.dumps(outs, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
