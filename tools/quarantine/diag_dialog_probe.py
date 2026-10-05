# -*- coding: utf-8 -*-
"""检测游戏进程名下的对话框(#32770) — ReplayDnD ReadReplay失败会弹WARN。"""
import sys, os, time, subprocess, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
user32 = ctypes.windll.user32

GAME = r'D:\temp\soku_arch\game_extract'
EXE = os.path.join(GAME, 'th123.exe')

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def all_windows(pid):
    out = []
    def cb(h, l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cls, 64)
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            out.append((cls.value, buf.value))
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out

env = {k: v for k, v in os.environ.items() if not k.startswith('SOKUAI')}
proc = subprocess.Popen([EXE, 'obstest0.rep'], cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d (ReplayDnD-only + rep argv)' % proc.pid)
t0 = time.time()
seen = set()
try:
    while time.time() - t0 < 45:
        if proc.poll() is not None:
            print('[退出 t+%.0fs] code=%s' % (time.time() - t0, proc.returncode))
            break
        for cls, title in all_windows(proc.pid):
            key = (cls, title)
            if key not in seen:
                seen.add(key)
                print('t+%3ds 窗口 class=%r title=%r' % (round(time.time() - t0), cls, title))
        time.sleep(0.5)
finally:
    if proc.poll() is None:
        proc.kill()
        print('[已清理]')
