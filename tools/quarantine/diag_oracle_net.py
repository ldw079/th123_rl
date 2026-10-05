# -*- coding: utf-8 -*-
"""神谕连接诊断: 监控窗口标题(Game on port N?) + netstat连接状态。"""
import sys, os, time, json, subprocess, shutil, socket, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
user32 = ctypes.windll.user32

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ORIG_ML = r'D:\touhou\hisoutensoku2026-06-15\th123\ModLoaderSettings.json'
ML = os.path.join(GAME, 'ModLoaderSettings.json')
PORT = 20982
OFF = ['giuroll', 'SokuAIOfflinePlayer', 'PracticeEX', 'SokuLobbiesMod',
       'IPv6MapSokuMod', 'UPnPNat']

orig = json.load(open(ORIG_ML, encoding='utf-8-sig'))['modules']
d = {'modules': {}}
for k, v in orig.items():
    en = bool(v.get('enabled'))
    for c in OFF:
        if c.lower() in k.lower():
            en = False
    d['modules'][k] = {'enabled': en}
d['modules'][r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll'] = {'enabled': True}
json.dump(d, open(ML, 'w', encoding='utf-8-sig'), indent=4)
print('[配置] 已写')

shutil.copy(r'D:\temp\soku_arch\game_extract\obstest0.rep', os.path.join(GAME, 'oracle.rep'))

lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
lsock.bind(('127.0.0.1', PORT))
lsock.listen(1)
print('[python] 监听 %d' % PORT)

env = {**os.environ, 'SOKUAI_PORT': str(PORT), 'SOKUAI_OBSERVE': '1',
       'SOKUAI_TRACE': '1'}
proc = subprocess.Popen([EXE, 'oracle.rep'], cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d' % proc.pid)

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def titles(pid):
    out = []
    def cb(h, l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            if buf.value:
                out.append(buf.value)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out

t0 = time.time()
seen_title = set()
connected = False
sock = None
try:
    while time.time() - t0 < 100:
        if proc.poll() is not None:
            print('[退出 t+%.0fs code=%s]' % (time.time() - t0, proc.returncode))
            break
        for t in titles(proc.pid):
            if t not in seen_title:
                seen_title.add(t)
                print('t+%3ds 标题: %r' % (round(time.time() - t0), t))
        ns = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                            encoding='gbk', errors='replace').stdout
        conns = [ln.strip() for ln in ns.splitlines()
                 if str(PORT) in ln and str(proc.pid) in ln]
        if conns:
            print('t+%3ds netstat: %s' % (round(time.time() - t0), conns[:3]))
        if not connected:
            try:
                lsock.settimeout(0.3)
                sock, peer = lsock.accept()
                connected = True
                print('t+%3ds [连接!] %s' % (round(time.time() - t0), peer))
            except socket.timeout:
                pass
        time.sleep(1)
finally:
    if sock:
        sock.close()
    lsock.close()
    if proc.poll() is None:
        proc.kill()
        print('[已清理]')
