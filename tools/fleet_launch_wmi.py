# -*- coding: utf-8 -*-
"""P0 预防: 常驻 fleet 统一 WMI detached 启动（禁止工具 shell Start-Process）.

用法:
  python tools/fleet_launch_wmi.py [--check] [--wait 150]
--check: only detached parent-chain check (supervisor parent should be gone/WmiPrvSE).
"""
import argparse
import base64
import json
import subprocess
import sys
import time

BAT = r'D:\temp\train_batch_launch.bat'


def _ps(script):
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', enc],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    return (r.stdout or '').strip(), (r.stderr or '').strip()


def launch():
    script = (
        "$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        "-Arguments @{CommandLine='cmd.exe /c %s'}; "
        "Write-Output ('ret='+$r.ReturnValue+' pid='+$r.ProcessId)" % BAT)
    out, err = _ps(script)
    print('[wmi-launch]', out, err[:200])
    return 'ret=0' in out


def check():
    script = (
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "
        "'python.exe' -and $_.CommandLine -match 'fleet_supervisor' } | "
        "ForEach-Object { $pp=Get-CimInstance Win32_Process -Filter "
        "('ProcessId='+$_.ParentProcessId) -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{pid=$_.ProcessId; parent=$_.ParentProcessId; "
        "parent_name=$(if($pp){$pp.Name}else{'gone'})} } | "
        "ConvertTo-Json -Compress")
    out, err = _ps(script)
    print('[detached-check]', out[:400], err[:120])
    try:
        d = json.loads(out) if out else {}
        rows = d if isinstance(d, list) else [d]
        ok = bool(rows) and all(
            str(r.get('parent_name')) in ('gone', 'WmiPrvSE.exe', 'WmiPrvSE')
            for r in rows)
    except Exception:
        ok = False
    print('[detached-check]', 'PASS (detached)' if ok else 'FAIL/SUSPECT')
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--wait', type=int, default=0)
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check() else 1)
    launch()
    if a.wait:
        time.sleep(a.wait)
    check()
    return 0


if __name__ == '__main__':
    sys.exit(main())
