# -*- coding: utf-8 -*-
"""神谕提速验证: tps=480 重跑obstest0, 与实时npz逐帧比对。
确定则提速可用(批量提取8x提速)。"""
import sys, os, time, json, subprocess, shutil, socket, struct, ctypes
import numpy as np
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
from soku_arch.trainer_client import TrainerClient

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ML = os.path.join(GAME, 'ModLoaderSettings.json')
PORT = 20962
TPS = 480
ORACLE_SET = [r'modules\MemoryPatch\MemoryPatch.dll',
              r'modules\ReplayDnD-old\ReplayDnD-old.dll',
              r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll',
              r'modules\ChainCFix\ChainCFix.dll',
              r'modules\FixMeiling236\FixMeiling236.dll']

d = {'modules': {m: {'enabled': True} for m in ORACLE_SET}}
json.dump(d, open(ML, 'w', encoding='utf-8-sig'), indent=4)
shutil.copy(r'D:\temp\soku_arch\game_extract\obstest0.rep' if os.path.exists(
    r'D:\temp\soku_arch\game_extract\obstest0.rep') else
    r'D:\temp\expert_reps\123(铃仙)_zoe(黑白)_2025-07-06-11-50-14__25-07-03_21-12-23_123__(铃仙)_zoe(魔理沙)_(0︰2_负).rep',
    os.path.join(GAME, 'oracle.rep'))

cli = TrainerClient(PORT, EXE, GAME, launch=True, accept_timeout=90,
                    raw_argv=['oracle.rep'],
                    env={'SOKUAI_PORT': str(PORT), 'SOKUAI_OBSERVE': '1'})
rows, rounds = [], []
prev = (0, 0)
t0 = time.time()
try:
    cli.handshake()
    cli.set_speed(TPS)
    print('[握手+提速%d OK t+%.0fs]' % (TPS, time.time() - t0))
    last_rx = t0
    while time.time() - t0 < 600:
        if cli.proc and cli.proc.poll() is not None:
            print('[进程退出 t+%.0fs]' % (time.time() - t0))
            break
        try:
            kind, payload = cli.poll(timeout=3.0)
        except TimeoutError:
            if time.time() - last_rx > 45:
                print('[空闲45s 停止] 共%d帧' % len(rows))
                break
            continue
        except Exception as e:
            print('[异常] %s' % e)
            break
        last_rx = time.time()
        if kind == 'fault':
            print('[崩溃] %s @%d' % (payload, len(rows)))
            break
        if kind in ('error', 'ended'):
            print('[%s] %s' % (kind, payload))
            if kind == 'ended':
                continue
            break
        if kind == 'frame':
            L, R, W = payload['left'], payload['right'], payload['weather']
            rows.append((L['hp'], R['hp'], int(L['position.x'] * 10),
                         int(R['position.x'] * 10), L['action'], R['action'],
                         L['score'], R['score'], W['displayed'], W['active'],
                         W['timer']))
            sl, sr = L['score'], R['score']
            if (sl, sr) != prev:
                print('  [回合] 帧%d %d:%d (t+%.0fs)' % (len(rows), sl, sr, time.time() - t0))
                rounds.append((len(rows), sl, sr))
                prev = (sl, sr)
finally:
    cli.close()

print('\ntps480: %d帧 回合=%s 用时%.0fs (实时版用了~302s)' % (
    len(rows), rounds, time.time() - t0))
orc = np.load(r'D:\temp\oracle_obstest0.npz')['x']
n = min(len(rows), len(orc))
first_div = next((i for i in range(n) if tuple(rows[i]) != tuple(int(v) for v in orc[i])), None)
print('实时流%d帧 vs 提速流%d帧: 首个分叉=%s' % (len(orc), len(rows),
      first_div if first_div is not None else '无(逐帧一致!)'))
np.savez(r'D:\temp\oracle_obstest0_tps480.npz', x=np.array(rows, dtype=np.float64),
         rounds=np.array(rounds))
