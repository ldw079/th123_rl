# -*- coding: utf-8 -*-
"""WMI detached 行为探针（P0 预防证据）: 起 dummy→验父进程→按 PID 清理.

用法: python tools/fleet_wmi_probe.py [--json]
"""
import base64
import json
import os
import subprocess
import sys
import tempfile


def probe():
    script = r'''
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c ping -n 20 127.0.0.1'}
Start-Sleep -Milliseconds 800
$p1 = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $r.ProcessId)
$pp = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p1.ParentProcessId) -ErrorAction SilentlyContinue
$d = [pscustomobject]@{pid=$r.ProcessId; parent=$p1.ParentProcessId; parent_name=$(if($pp){$pp.Name}else{'gone'})}
Write-Output ('json:' + ($d | ConvertTo-Json -Compress))
'''
    fd, fp = tempfile.mkstemp(suffix='.ps1')
    os.close(fd)
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(script)
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy',
                            'Bypass', '-File', fp], capture_output=True,
                           text=True, timeout=120)
    finally:
        try:
            os.remove(fp)
        except OSError:
            pass
    d = {}
    for line in (r.stdout or '').splitlines():
        if line.startswith('json:'):
            try:
                d = json.loads(line[5:])
            except Exception:
                d = {}
    if d.get('pid'):
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(int(d['pid']))],
                       capture_output=True, timeout=30)
    return d


def detached(d):
    return (bool(d.get('pid'))
            and str(d.get('parent_name')) in ('WmiPrvSE.exe', 'cmd.exe'))


def main():
    d = probe()
    ok = detached(d)
    print('[probe]', 'PASS' if ok else 'FAIL',
          json.dumps(d, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
