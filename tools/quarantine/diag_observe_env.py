# -*- coding: utf-8 -*-
"""observe式启动诊断: 窗口标题 / trace增长 / 连接。"""
import sys, os, time, subprocess, socket, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe

GAME = r'D:\temp\soku_arch\game_extract'
EXE = os.path.join(GAME, 'th123.exe')
PORT = 20976
TRACE = r'D:\temp\soku_arch\logs\mod_trace.log'

t_before = os.path.getsize(TRACE) if os.path.exists(TRACE) else 0

lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
lsock.bind(('127.0.0.1', PORT))
lsock.listen(1)
print('[python] 已监听 %d (trace起点 %d 字节)' % (PORT, t_before))

env = {**os.environ, 'SOKUAI_PORT': str(PORT), 'SOKUAI_OBSERVE': '1',
       'SOKUAI_TRACE': '1'}
proc = subprocess.Popen([EXE, 'obstest0.rep'], cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d  env含 SOKUAI_PORT=%s SOKUAI_OBSERVE=1' % (proc.pid, PORT))

lsock.settimeout(90)
connected = False
title = None
for t in range(90):
    time.sleep(1)
    if title is None:
        hwnd = win_probe.find_window(proc.pid)
        if hwnd:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            txt = buf.value
            if txt:
                title = txt
                print('[标题 t+%ds] %r' % (t, txt))
    if title is not None and t % 10 == 0:
        hwnd = win_probe.find_window(proc.pid)
        if hwnd:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            print('[标题 t+%ds] %r' % (t, buf.value))
    if not connected:
        try:
            lsock.settimeout(0.3)
            sock, peer = lsock.accept()
            connected = True
            print('[连接 t+%ds] %s —— mod 已回连!' % (t, peer))
            sock.close()
            break
        except socket.timeout:
            pass
    if proc.poll() is not None:
        print('[进程退出 t+%ds] code=%s' % (t, proc.returncode))
        break

time.sleep(2)
t_after = os.path.getsize(TRACE)
print('[trace] %d -> %d 字节 (增长 %d)' % (t_before, t_after, t_after - t_before))
if t_after > t_before:
    with open(TRACE, 'r', encoding='utf8', errors='replace') as f:
        f.seek(t_before)
        print('[trace新增]\n' + f.read()[-1500:])
if not connected:
    print('[结论] mod 未回连')
try:
    lsock.close()
except OSError:
    pass
if proc.poll() is None:
    proc.kill()
