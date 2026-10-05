# -*- coding: utf-8 -*-
"""在用户自己的游戏目录里测 rep argv 加载(完整整合包环境)。"""
import sys, os, time, subprocess, shutil, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
from soku_arch import win_probe
user32 = ctypes.windll.user32

GAME = r'D:\touhou\hisoutensoku2026-06-15\th123'
EXE = os.path.join(GAME, 'th123.exe')
SRC = sys.argv[1]
NAME = sys.argv[2] if len(sys.argv) > 2 else 'loadtest.rep'
DUR = int(sys.argv[3]) if len(sys.argv) > 3 else 45

shutil.copy(SRC, os.path.join(GAME, NAME))
print('[暂存] -> %s (游戏目录根)' % NAME)

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def dialog_texts(pid):
    out = []
    def cb(h, l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cls, 64)
            if cls.value == '#32770':
                def cb2(c, l2):
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(c, buf, 512)
                    if buf.value:
                        out.append(buf.value)
                    return True
                user32.EnumChildWindows(h, WNDENUMPROC(cb2), 0)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out

env = {k: v for k, v in os.environ.items() if not k.startswith('SOKUAI')}
proc = subprocess.Popen([EXE, NAME], cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d (用户游戏目录)' % proc.pid)
h = None
last_scene = object()
t0 = time.time()
try:
    while time.time() - t0 < DUR:
        if proc.poll() is not None:
            print('[退出 t+%.0fs] code=%s' % (time.time() - t0, proc.returncode))
            break
        hwnd = win_probe.find_window(proc.pid)
        if hwnd and round(time.time() - t0) <= 12:
            win_probe.force_foreground(hwnd)
        if h is None:
            try:
                h = win_probe.open_for_write(proc.pid)
            except Exception:
                h = None
        if h:
            try:
                s = win_probe.read_u8(h, win_probe.SCENE_ADDR)
                if s != last_scene:
                    print('t+%3ds scene=%s' % (round(time.time() - t0), s))
                    last_scene = s
            except Exception:
                pass
        dt = dialog_texts(proc.pid)
        if dt:
            print('t+%3ds 对话框: %r' % (round(time.time() - t0), dt[:3]))
            break
        time.sleep(1)
finally:
    if h:
        win_probe.k32.CloseHandle(ctypes.c_void_p(h))
    if proc.poll() is None:
        proc.kill()
        print('[已清理]')
