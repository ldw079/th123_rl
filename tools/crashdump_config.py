# -*- coding: utf-8 -*-
"""Crash dump 配置检查/设置（DedicatedDumpFile 落 D 盘，避免仅 D 页文件无法落盘）.

用法: python tools/crashdump_config.py [--check|--apply]
非管理员时 apply 会失败并如实记录（15:00 窗以管理员/记录为准）。
"""
import argparse
import json
import os
import sys

KEY = r"SYSTEM\\CurrentControlSet\\Control\\CrashControl"
OUT = r'D:\temp\crashdump_config_20261026.json'


def read_current():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, KEY)
        names = ['CrashDumpEnabled', 'AutoReboot', 'DumpFile',
                 'DedicatedDumpFile', 'DumpFileSize']
        out = {}
        for n in names:
            try:
                out[n] = winreg.QueryValueEx(k, n)[0]
            except OSError:
                out[n] = None
        winreg.CloseKey(k)
        return out
    except Exception as e:
        return {'error': repr(e)}


def pagefile():
    try:
        import subprocess
        r = subprocess.run(['powershell', '-NoProfile', '-Command',
                            'Get-CimInstance Win32_PageFileUsage | % { '
                            '$_.Name + \"|\" + $_.AllocatedBaseSize }'],
                           capture_output=True, text=True, timeout=30)
        return (r.stdout or '').strip()
    except Exception as e:
        return 'error:%r' % e


def apply(dump=r'D:\temp\dedicated.dmp', size_mb=2048):
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, KEY, 0,
                           winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, 'DedicatedDumpFile', 0, winreg.REG_SZ, dump)
        winreg.SetValueEx(k, 'DumpFileSize', 0, winreg.REG_DWORD, int(size_mb))
        winreg.SetValueEx(k, 'CrashDumpEnabled', 0, winreg.REG_DWORD, 3)
        winreg.CloseKey(k)
        return True, 'applied'
    except Exception as e:
        return False, repr(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    cur = read_current()
    rep = {'current': cur, 'pagefile': pagefile()}
    if a.apply:
        ok, msg = apply()
        rep['apply'] = {'ok': ok, 'msg': msg}
        rep['after'] = read_current()
    try:
        open(OUT, 'w').write(json.dumps(rep, ensure_ascii=False, indent=1))
    except OSError:
        pass
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
