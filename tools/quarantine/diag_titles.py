# -*- coding: utf-8 -*-
import ctypes, time, os, sys
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def titles():
    out = []
    def cb(h, l):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        if buf.value and pid.value:
            out.append((pid.value, buf.value))
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out
for pid, t in titles():
    print(pid, repr(t))
p = r'D:\temp\soku_arch\logs\mod_trace.log'
print('trace mtime', time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(p))))
print(open(p, encoding='utf8', errors='replace').read()[-500:])
