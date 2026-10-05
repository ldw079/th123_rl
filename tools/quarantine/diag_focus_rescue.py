# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
import ctypes
h = win_probe.open_for_write(18452)
for i in range(4):
    print('t+%d scene=%s' % (i * 5, win_probe.read_u8(h, win_probe.SCENE_ADDR)))
    time.sleep(5)
hwnd = win_probe.find_window(18452)
print('hwnd=%s -> 强制前台' % hwnd)
if hwnd:
    win_probe.force_foreground(hwnd)
time.sleep(15)
print('t+35 scene=%s' % win_probe.read_u8(h, win_probe.SCENE_ADDR))
