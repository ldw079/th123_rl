# -*- coding: utf-8 -*-
"""环境二分: 可控启用哪些模块/配置, 测ReplayDnD加载。"""
import json, os, shutil, sys, time, subprocess, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
from soku_arch import win_probe
user32 = ctypes.windll.user32

GAME = r'D:\temp\soku_arch\game_extract'
EXE = os.path.join(GAME, 'th123.exe')
INI = os.path.join(GAME, 'SWRSToys.ini')
CFG = os.path.join(GAME, 'config123.dat')
ML = os.path.join(GAME, 'ModLoaderSettings.json')

MODS = {
    'memorypatch': ('Mod0=modules/MemoryPatch/MemoryPatch.dll',
                    ';Mod0=modules/MemoryPatch/MemoryPatch.dll'),
    'replaydnd': ('Mod1=modules/ReplayDnD/ReplayDnD.dll',
                  ';Mod1=modules/ReplayDnD/ReplayDnD.dll'),
}

def set_ini(enable):
    s = open(INI, encoding='utf-8').read()
    for key, (on, off) in MODS.items():
        want = on if (key in enable) else off
        other = off if (key in enable) else on
        if other in s:
            s = s.replace(other, want)
    open(INI, 'w', encoding='utf-8').write(s)

def set_json(enable):
    d = json.load(open(ML, encoding='utf-8-sig'))
    m = r'modules\MemoryPatch\MemoryPatch.dll'
    r = r'modules\ReplayDnD\ReplayDnD.dll'
    d['modules'][m]['enabled'] = 'memorypatch' in enable
    d['modules'][r]['enabled'] = 'replaydnd' in enable
    json.dump(d, open(ML, 'w', encoding='utf-8-sig'), indent=4)

def move_config(fresh):
    if fresh:
        if os.path.exists(CFG):
            os.rename(CFG, CFG + '.bak')
    else:
        if os.path.exists(CFG + '.bak'):
            os.rename(CFG + '.bak', CFG)

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

def run_case(name, enable, fresh_cfg, rep, dur=40):
    print('\n=== %s: mods=%s fresh_cfg=%s rep=%s ===' % (name, enable, fresh_cfg, rep))
    set_ini(enable)
    set_json(enable)
    move_config(fresh_cfg)
    src = os.path.join(GAME, 'vanillatest.rep')
    for dst in (os.path.join(GAME, rep), os.path.join(GAME, 'replay', rep)):
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy(src, dst)
    env = {k: v for k, v in os.environ.items() if not k.startswith('SOKUAI')}
    proc = subprocess.Popen([EXE, rep], cwd=GAME, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    h = None
    last_scene = object()
    t0 = time.time()
    result = 'no-dialog'
    try:
        while time.time() - t0 < dur:
            if proc.poll() is not None:
                print('  [退出 t+%.0fs code=%s]' % (time.time() - t0, proc.returncode))
                break
            hwnd = win_probe.find_window(proc.pid)
            if hwnd:
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
                        print('  t+%3ds scene=%s' % (round(time.time() - t0), s))
                        last_scene = s
                except Exception:
                    pass
            dt = dialog_texts(proc.pid)
            if dt:
                print('  t+%3ds 对话框: %r' % (round(time.time() - t0), dt[:3]))
                result = 'dialog:' + (dt[-1] if dt else '')
                break
            time.sleep(1)
    finally:
        if h:
            win_probe.k32.CloseHandle(ctypes.c_void_p(h))
        if proc.poll() is None:
            proc.kill()
    print('  => %s' % result)
    return result


results = {}
results['T1'] = run_case('T1 只有ReplayDnD', ['replaydnd'], False, 'vanillatest.rep')
results['T2'] = run_case('T2 RnD+新config', ['replaydnd'], True, 'vanillatest.rep')
results['T3'] = run_case('T3 MP+RnD+新config', ['memorypatch', 'replaydnd'], True,
                         'vanillatest.rep')
move_config(False)
print('\n汇总:', results)
