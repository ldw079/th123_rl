# -*- coding: utf-8 -*-
"""崩溃时: 用 tasklist /m 抓32位进程模块表, 映射出错地址。"""
import sys, os, re, time, json, subprocess, shutil, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
from soku_arch import win_probe
user32 = ctypes.windll.user32

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ORIG_ML = r'D:\touhou\hisoutensoku2026-06-15\th123\ModLoaderSettings.json'
ML = os.path.join(GAME, 'ModLoaderSettings.json')

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

def modules_via_tasklist(pid):
    r = subprocess.run(['tasklist', '/m', '/fi', 'PID eq %d' % pid],
                       capture_output=True, text=True, encoding='gbk',
                       errors='replace')
    names = [ln.split('=')[-1].strip() for ln in r.stdout.splitlines()
             if ',' in ln or '.dll' in ln.lower()]
    mods = []
    for ln in r.stdout.splitlines():
        m = re.match(r'^(\S+)\s+\d+\D+(\d[\d,]+) K\s+(.*)$', ln)
        if m:
            mods.append((m.group(1), m.group(3).strip()))
    return mods

orig = json.load(open(ORIG_ML, encoding='utf-8-sig'))['modules']
d = {'modules': {k: {'enabled': bool(v.get('enabled'))} for k, v in orig.items()}}
json.dump(d, open(ML, 'w', encoding='utf-8-sig'), indent=4)

shutil.copy(r'D:\touhou\hisoutensoku2026-06-15\th123\replay\story\260627_1031_sanae_story.rep',
            os.path.join(GAME, 'rlt.rep'))
env = {k: v for k, v in os.environ.items() if not k.startswith('SOKUAI')}
proc = subprocess.Popen([EXE, 'rlt.rep'], cwd=GAME, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
print('[启动] pid=%d' % proc.pid)
t0 = time.time()
try:
    while time.time() - t0 < 60:
        if proc.poll() is not None:
            print('[退出] code=%s' % proc.returncode)
            break
        hwnd = win_probe.find_window(proc.pid)
        if hwnd and time.time() - t0 <= 12:
            win_probe.force_foreground(hwnd)
        dt = dialog_texts(proc.pid)
        if dt:
            txt = ' '.join(dt)
            print('对话框: %r' % txt[:180])
            m = re.search(r'address ([0-9a-fA-F]{8})', txt)
            addr = int(m.group(1), 16) if m else None
            mods = modules_via_tasklist(proc.pid)
            print('模块数=%d, 地址=%s' % (len(mods),
                  ('0x%08X' % addr) if addr else '?'))
            for name, extra in mods:
                if name.lower().endswith('.dll') or name.lower().startswith('th123'):
                    print('  %s' % name)
            break
        time.sleep(1)
finally:
    if proc.poll() is None:
        proc.kill()
        print('[已清理]')
