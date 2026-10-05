# -*- coding: utf-8 -*-
"""神谕: rl_game(用户整合包环境-崩溃mod) 自播rep + 被动mod收状态流。

用法: oracle_observe.py <rep绝对路径> <端口> <输出npz> [--full]
监听 mod 被动推送的帧, 记录hp/score/回合事件, 落盘npz。
"""
import sys, os, time, json, subprocess, shutil, socket, struct, ctypes
import numpy as np
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
from soku_arch.trainer_client import TrainerClient
from soku_arch.packet_schema import CS_SIZE

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ORIG_ML = r'D:\touhou\hisoutensoku2026-06-15\th123\ModLoaderSettings.json'
ML = os.path.join(GAME, 'ModLoaderSettings.json')
CRASHERS = None   # 改用白名单
ORACLE_SET = [r'modules\MemoryPatch\MemoryPatch.dll',
              r'modules\ReplayDnD-old\ReplayDnD-old.dll',
              r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll',
              r'modules\ChainCFix\ChainCFix.dll',
              r'modules\FixMeiling236\FixMeiling236.dll']


def apply_cfg(port):
    # R38(第九轮审计§2.2): 原utf-8-sig(BOM)+反斜杠键违反加载器格式纪律
    # (AGENTS.md:22-27) — 与oracle_batch2同款正确写法: utf-8无BOM+正斜杠键
    d = {'modules': {'modules/%s/%s.dll' % (m, m): {'enabled': True}
                     for m in ('MemoryPatch', 'ReplayDnD-old',
                               'SokuAITrainerEnv', 'ChainCFix',
                               'FixMeiling236')}}
    json.dump(d, open(ML, 'w', encoding='utf-8', newline=''), indent=4)
    print('[配置] 神谕集 %d 个' % len(d['modules']))


def main():
    rep = os.path.abspath(sys.argv[1])
    port = int(sys.argv[2])
    out = sys.argv[3]
    full = '--full' in sys.argv
    apply_cfg(port)

    name = 'oracle.rep'
    shutil.copy(rep, os.path.join(GAME, name))

    # 第八轮审查§7.3: oracle通道端口限定probe段(20960-20999), 防串流live训练
    assert 20960 <= port <= 20999, \
        "oracle端口 %d 越出 probe 段 [20960,20999]" % port

    cli = TrainerClient(port, EXE, GAME, launch=True, accept_timeout=90,
                        raw_argv=[name],
                        env={'SOKUAI_PORT': str(port), 'SOKUAI_OBSERVE': '1',
                             'SOKUAI_TRACE': '1'})
    rows, rounds = [], []
    prev = (0, 0)
    t0 = time.time()
    last_rx = t0
    try:
        cli.handshake()
        print('[握手] OK t+%.0fs' % (time.time() - t0))
        while time.time() - t0 < 900:
            if cli.proc and cli.proc.poll() is not None:
                print('[进程退出 t+%.0fs code=%s]' % (time.time() - t0,
                                                      cli.proc.returncode))
                break
            try:
                kind, payload = cli.poll(timeout=3.0)
            except TimeoutError:
                if time.time() - last_rx > 120:
                    print('[空闲120s 停止] t+%.0fs 共%d帧' % (time.time() - t0, len(rows)))
                    break
                continue
            except Exception as e:
                print('[读异常] %s' % e)
                break
            last_rx = time.time()
            if kind == 'fault':
                print('[崩溃包] %s @帧%d' % (payload, len(rows)))
                break
            if kind == 'ended':
                print('[终局] %s @帧%d' % (payload, len(rows)))
                break
            if kind == 'error':
                print('[错误码] %s' % payload)
                break
            if kind == 'frame':
                L, R, W = payload['left'], payload['right'], payload['weather']
                rows.append((L['hp'], R['hp'], int(L['position.x'] * 10),
                             int(R['position.x'] * 10), L['action'], R['action'],
                             L['score'], R['score'], W['displayed'], W['active'],
                             W['timer']))
                sl, sr = L['score'], R['score']
                if (sl, sr) != prev:
                    print('  [回合事件] 帧%d: %d:%d (t+%.0fs)' % (
                        len(rows), sl, sr, time.time() - t0))
                    rounds.append((len(rows), sl, sr))
                    prev = (sl, sr)
                if len(rows) % 2000 == 0:
                    print('  [进度] %d帧 hp=%s/%s score=%d:%d w=%s/%s t+%.0fs' % (
                        len(rows), L['hp'], R['hp'], sl, sr,
                        W['displayed'], W['active'], time.time() - t0))
    finally:
        cli.close()
    if rows:
        x = np.array(rows, dtype=np.float64)
        np.savez(out, x=x, rounds=np.array(rounds),
                 meta=np.array(json.dumps({'rep': os.path.basename(rep),
                                           'frames': len(rows),
                                           'rounds': rounds})))
        print('[产物] %s  %d帧  回合事件 %s' % (out, len(rows), rounds))
        scL, scR = rows[-1][6], rows[-1][7]
        print('[终态] score=%d:%d hp=%s/%s' % (scL, scR, rows[-1][0], rows[-1][1]))
    else:
        # R38(第九轮审计§2.2): 空收帧exit 0让自动化无法察觉失败 — 响亮失败
        print('[空] 一帧未收')
        sys.exit(1)


if __name__ == '__main__':
    main()
