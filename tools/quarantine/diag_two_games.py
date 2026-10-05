# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
for pid in (13180, 11536):
    try:
        h = win_probe.open_for_write(pid)
        s = win_probe.read_u8(h, win_probe.SCENE_ADDR)
        win_probe.k32.CloseHandle
        print('pid %d scene=%s' % (pid, s))
    except Exception as e:
        print('pid %d ERR %s' % (pid, e))
import os
p = r'D:\temp\soku_arch\logs\mod_trace.log'
print('trace mtime', time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(p))))
print(open(p, encoding='utf8', errors='replace').read()[-400:])
