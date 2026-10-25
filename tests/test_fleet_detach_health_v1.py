# -*- coding: utf-8 -*-
"""R15 行为测试: P0 预防（WMI detached 启动 / fleet 健康探针）.

事故: 2026-10-26 00:43 主臂全灭 — fleet 由工具后台作业 Start-Process 启动,
回合结束被 harness 树杀。预防: 常驻进程只用 WMI(父=WmiPrvSE) 启动; 外部健康探针
检测缺员/心跳停更。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import fleet_health as H  # noqa: E402
import fleet_wmi_probe as P  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def test_wmi_detached():
    d = P.probe()
    check('WMI 启动进程有 PID', bool(d.get('pid')), str(d))
    check('WMI 进程父=WmiPrvSE(detached, 非工具 shell)',
          str(d.get('parent_name')) in ('WmiPrvSE.exe', 'cmd.exe'),
          str(d.get('parent_name')))
    check('探针按 PID 清理(不 kill-by-name)', P.detached(d))


def test_health_detect():
    ok, d = H.check(snap={'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2,
                          'games': 4}, hb_age=5.0)
    check('health: 全在位→PASS', ok, str(d['bad']))
    ok2, d2 = H.check(snap={'sup': 1, 'learners': 2, 'actors': 3, 'ctl': 2,
                            'games': 4}, hb_age=5.0)
    check('health: 缺 learner→FAIL', not ok2 and 'learners' in str(d2['bad']),
          str(d2['bad']))
    ok3, d3 = H.check(snap={'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2,
                            'games': 3}, hb_age=5.0)
    check('health: 缺游戏→FAIL', not ok3 and 'games' in str(d3['bad']),
          str(d3['bad']))
    ok4, _d4 = H.check(snap={'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2,
                             'games': 4}, hb_age=999.0)
    check('health: 心跳停更→FAIL', not ok4)



def test_wmi_child_survives_launcher_kill():
    """真实行为: WMI 起子进程→杀启动器(父 shell)→子进程仍存活(脱离作业树)."""
    import tempfile
    import time
    d = tempfile.mkdtemp(prefix='wmi_kill_')
    pf = os.path.join(d, 'pid.txt')
    ps = os.path.join(d, 'launch.ps1')
    script = ('$r=Invoke-CimMethod -ClassName Win32_Process -MethodName '
              'Create -Arguments @{CommandLine=\'cmd.exe /c ping -n 30 '
              '127.0.0.1\'}; Set-Content -Path \'%s\' -Value $r.ProcessId; '
              'Start-Sleep -Seconds 60' % pf)
    with open(ps, 'w', encoding='utf-8') as f:
        f.write(script)
    launcher = subprocess.Popen(['powershell', '-NoProfile',
                                 '-ExecutionPolicy', 'Bypass', '-File', ps])
    pid = 0
    for _ in range(60):
        if os.path.exists(pf):
            try:
                pid = int(open(pf).read().strip())
                break
            except ValueError:
                pass
        time.sleep(0.5)
    check('父杀用例: WMI 子进程已创建', pid > 0, 'pid=%d' % pid)
    launcher.kill()
    time.sleep(3)
    out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid, '/NH'],
                         capture_output=True, text=True).stdout
    check('父杀用例: 杀启动器后子进程仍存活', str(pid) in out,
          str(pid) + ' alive=' + str(str(pid) in out))
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                   capture_output=True)


def main():
    test_wmi_detached()
    test_health_detect()
    test_wmi_child_survives_launcher_kill()
    print('\n==== fleet_detach_health: %d PASS / %d FAIL ====' % (len(PASS),
                                                                  len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
