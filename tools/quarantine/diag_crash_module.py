# -*- coding: utf-8 -*-
"""崩溃时: 解析对话框里的出错地址, 映射到所在DLL。"""
import sys, os, re, time, json, subprocess, shutil, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
from soku_arch import win_probe
user32 = ctypes.windll.user32
psapi = ctypes.windll.psapi
kernel32 = ctypes.windll.kernel32

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

def module_of(pid, addr):
    PROCESS_QUERY_INFORMATION = 0x400
    PROCESS_VM_READ = 0x10
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return 'OpenProcess失败'
    arr = (wintypes.HMODULE * 2048)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModules(h, arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        kernel32.CloseHandle(h)
        return 'EnumProcessModules失败'
    n = needed.value // ctypes.sizeof(wintypes.HMODULE)
    mods = []
    psapi.GetModuleFileNameExW.restype = ctypes.c_int
    for i in range(n):
        base32 = int(arr[i]) & 0xFFFFFFFF
        name = ctypes.create_unicode_buffer(512)
        psapi.GetModuleFileNameExW(ctypes.c_void_p(h), ctypes.c_void_p(base32),
                                   name, 512)
        if name.value:
            mods.append((base32, name.value))
    kernel32.CloseHandle(h)
    best = None
    for base, name in mods:
        if base <= addr:
            if best is None or base > best[0]:
                best = (base, name)
    if best is None:
        return '未找到(%d个模块)' % n
    return '%s +0x%X' % (os.path.basename(best[1]), addr - best[0])

# 恢复完整模块表
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
            print('对话框: %r' % txt[:200])
            m = re.search(r'address ([0-9a-fA-F]{8})', txt)
            if m:
                addr = int(m.group(1), 16)
                print('出错地址 0x%08X -> 模块: %s' % (addr, module_of(proc.pid, addr)))
            break
        time.sleep(1)
finally:
    if proc.poll() is None:
        proc.kill()
        print('[已清理]')
