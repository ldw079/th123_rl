# -*- coding: utf-8 -*-
"""连接二分: 指定模块子集, 测mod能否连上Python监听端口。"""
import sys, os, time, json, subprocess, shutil, socket, ctypes
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from ctypes import wintypes
user32 = ctypes.windll.user32

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ML = os.path.join(GAME, 'ModLoaderSettings.json')
PORT = 20983

def run_case(keep, dur=50):
    d = {'modules': {m: {'enabled': True} for m in keep}}
    json.dump(d, open(ML, 'w', encoding='utf-8-sig'), indent=4)
    print('== 保留: %s ==' % keep)
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.bind(('127.0.0.1', PORT))
    lsock.listen(1)
    env = {**os.environ, 'SOKUAI_PORT': str(PORT), 'SOKUAI_OBSERVE': '1',
           'SOKUAI_TRACE': '1'}
    proc = subprocess.Popen([EXE, 'oracle.rep'], cwd=GAME, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    t0 = time.time()
    connected = False
    sock = None
    while time.time() - t0 < dur:
        if proc.poll() is not None:
            print('  [退出 t+%.0fs code=%s]' % (time.time() - t0, proc.returncode))
            break
        try:
            lsock.settimeout(0.5)
            sock, peer = lsock.accept()
            connected = True
            print('  [连接 t+%.0fs] %s' % (time.time() - t0, peer))
            break
        except socket.timeout:
            pass
    if sock:
        sock.close()
    lsock.close()
    if proc.poll() is None:
        proc.kill()
    print('  => %s' % ('CONNECTED' if connected else 'no-conn'))
    time.sleep(2)
    return connected

if __name__ == '__main__':
    TRIO_OLD = [r'modules\MemoryPatch\MemoryPatch.dll',
                r'modules\ReplayDnD-old\ReplayDnD-old.dll',
                r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll']
    TRIO_NEW = [r'modules\MemoryPatch\MemoryPatch.dll',
                r'modules\ReplayDnD\ReplayDnD.dll',
                r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll']
    r1 = run_case(TRIO_OLD)
    r2 = run_case(TRIO_NEW)
    print('\nOLD三件套: %s   NEW三件套: %s' % (r1, r2))
