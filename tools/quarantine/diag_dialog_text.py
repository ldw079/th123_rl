# -*- coding: utf-8 -*-
"""读取 ReplayDnD 对话框的完整文本与按钮。"""
import sys, os, time, subprocess, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
user32 = ctypes.windll.user32

GAME = r'D:\temp\soku_arch\game_extract'
EXE = os.path.join(GAME, 'th123.exe')

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def find_dialog(pid):
    hits = []
    def cb(h, l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cls, 64)
            if cls.value == '#32770':
                hits.append(h)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return hits

def read_dialog(h):
    lines = []
    def cb2(child, l):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(child, cls, 64)
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(child, buf, 512)
        if buf.value:
            lines.append('%s: %r' % (cls.value, buf.value))
        return True
    user32.EnumChildWindows(h, WNDENUMPROC(cb2), 0)
    return lines

env = {k: v for k, v in os.environ.items() if not k.startswith('SOKUAI')}
proc = subprocess.Popen([EXE, 'obstest0.rep'], cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d' % proc.pid)
t0 = time.time()
try:
    while time.time() - t0 < 30:
        dlgs = find_dialog(proc.pid)
        if dlgs:
            for h in dlgs:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(h, buf, 256)
                print('对话框标题: %r' % buf.value)
                for ln in read_dialog(h):
                    print('  子控件 %s' % ln)
            break
        time.sleep(0.5)
    else:
        print('30s内未出现对话框')
finally:
    if proc.poll() is None:
        proc.kill()
        print('[已清理]')
