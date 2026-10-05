# -*- coding: utf-8 -*-
"""A2: ReplayDnD-only + rep argv + 强制前台, 看场景是否推进。"""
import sys, os, time, subprocess, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
from ctypes import wintypes

GAME = r'D:\temp\soku_arch\game_extract'
EXE = os.path.join(GAME, 'th123.exe')
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 240
ARGV = sys.argv[2] if len(sys.argv) > 2 else 'obstest0.rep'

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def win_title(pid):
    out = []
    def cb(h, l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            if buf.value:
                out.append(buf.value)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return ' | '.join(out[:3])

env = {k: v for k, v in os.environ.items() if not k.startswith('SOKUAI')}
argv = [EXE] + ([ARGV] if ARGV != 'NONE' else [])
proc = subprocess.Popen(argv, cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d argv=%s (ReplayDnD-only, 将持续置前台)' % (proc.pid, argv[1:]))

h = None
last_scene, last_title = object(), object()
t0 = time.time()
try:
    while time.time() - t0 < DUR:
        if proc.poll() is not None:
            print('[退出 t+%.0fs] code=%s' % (time.time() - t0, proc.returncode))
            break
        hwnd = win_probe.find_window(proc.pid)
        if hwnd:
            win_probe.force_foreground(hwnd)
        if h is None:
            try:
                h = win_probe.open_for_write(proc.pid)
            except Exception:
                h = None
        scene = None
        if h:
            try:
                scene = win_probe.read_u8(h, win_probe.SCENE_ADDR)
            except Exception:
                scene = None
        title = win_title(proc.pid)
        if scene != last_scene or title != last_title:
            print('t+%3ds scene=%s title=%r' % (round(time.time() - t0), scene, title))
            last_scene, last_title = scene, title
        time.sleep(1)
finally:
    if h:
        win_probe.k32.CloseHandle(ctypes.c_void_p(h))
    if proc.poll() is None:
        proc.kill()
        print('[已清理] 游戏进程被杀')
