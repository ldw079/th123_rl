# -*- coding: utf-8 -*-
"""在神谕环境(rl_game + ChainCFix + FixMeiling236)里用驱动管线重演同一rep,
与神谕流逐帧比对。验证: 驱动比分==0:2==文件名 且 逐帧一致 → 同步闭环。

用法: oracle_drive.py <rep路径> <端口> <swap:0|1>
"""
import sys, os, time, json, struct, ctypes
import numpy as np
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
from soku_arch.trainer_client import TrainerClient, OPCODE_START_GAME_VS_PLAYER
from soku_arch.input_codec import BattleInput, battle_to_trainer
from soku_arch.rep_file import parse_rep_file

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ML = os.path.join(GAME, 'ModLoaderSettings.json')
ORACLE_SET = [r'modules\MemoryPatch\MemoryPatch.dll',
              r'modules\ReplayDnD-old\ReplayDnD-old.dll',
              r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll',
              r'modules\ChainCFix\ChainCFix.dll',
              r'modules\FixMeiling236\FixMeiling236.dll']


def main():
    rep_path = sys.argv[1]
    port = int(sys.argv[2])
    swap = bool(int(sys.argv[3])) if len(sys.argv) > 3 else False   # 换角色+换输入(全镜像)
    iswap = bool(int(sys.argv[4])) if len(sys.argv) > 4 else False  # 仅换输入,角色不动
    delay = int(sys.argv[5]) if len(sys.argv) > 5 else 0            # 输入延迟帧数
    d = {'modules': {m: {'enabled': True} for m in ORACLE_SET}}
    json.dump(d, open(ML, 'w', encoding='utf-8-sig'), indent=4)
    print('[配置] 神谕集5mod, swap=%s iswap=%s delay=%d' % (swap, iswap, delay))

    rep = parse_rep_file(rep_path)
    print('[rep] %s 帧%d 种子%d char %d/%d' % (os.path.basename(rep_path),
          rep.n_frames, rep.seed, rep.char_x, rep.char_y))

    if not swap:
        lc, ld, lp = rep.char_x, list(rep.deck_x), rep.pal_x
        rc, rd, rp = rep.char_y, list(rep.deck_y), rep.pal_y
    else:
        lc, ld, lp = rep.char_y, list(rep.deck_y), rep.pal_y
        rc, rd, rp = rep.char_x, list(rep.deck_x), rep.pal_x

    cli = TrainerClient(port, EXE, GAME, launch=True,
                        env={'SOKUAI_PORT': str(port),
                             'SOKUAI_SEED': str(rep.seed)})
    rows, rounds = [], []
    prev = (0, 0)
    try:
        cli.handshake()
        hwnd = win_probe.find_window(cli.proc.pid)
        if hwnd:
            win_probe.force_foreground(hwnd)
        h = win_probe.open_for_write(cli.proc.pid)
        if h and win_probe.read_bytes(h, win_probe.TBL_ADDR, 8) != \
                struct.pack('<II', win_probe.MGR_ADDR, win_probe.MGR_ADDR):
            win_probe.write_bytes(h, win_probe.TBL_ADDR,
                                  struct.pack('<II', win_probe.MGR_ADDR,
                                              win_probe.MGR_ADDR))
        cli.wait_for_ready(max_wait=40.0)
        first = cli.start_game(lc, rc, left_deck=ld, right_deck=rd,
                               left_palette=lp, right_palette=rp,
                               opcode=OPCODE_START_GAME_VS_PLAYER, stage=0,
                               hook=lambda: None)
        def row(L, R, W):
            return (L['hp'], R['hp'], int(L['position.x'] * 10),
                    int(R['position.x'] * 10), L['action'], R['action'],
                    L['score'], R['score'], W['displayed'], W['active'],
                    W['timer'])
        rows.append(row(first['left'], first['right'], first['weather']))
        n = 0
        timeouts = 0
        t0 = time.time()
        neutral = {'A': False, 'B': False, 'C': False, 'D': False,
                   'SC': False, 'SW': False, 'H': 0, 'V': 0}
        for f, a, b in rep.frames():
            try:
                if f - delay < 0:
                    cli.send_inputs(neutral, neutral)
                else:
                    off = f - delay
                    a2, b2 = rep.inputs[2 * off], rep.inputs[2 * off + 1]
                    la, ra = (b2, a2) if (swap or iswap) else (a2, b2)
                    li, _ = battle_to_trainer(BattleInput(la))
                    ri, _ = battle_to_trainer(BattleInput(ra))
                    cli.send_inputs(li.as_dict(), ri.as_dict())
                kind, payload = cli.poll(timeout=5.0)
            except TimeoutError:
                timeouts += 1
                if timeouts > 30:
                    break
                continue
            if kind in ('fault', 'error'):
                print('[%s@帧%d] %s' % (kind, n, payload))
                break
            if kind == 'ended':
                print('[终局] %s @帧%d' % (payload, n))
                break
            rows.append(row(payload['left'], payload['right'], payload['weather']))
            n += 1
            sl, sr = payload['left']['score'], payload['right']['score']
            if (sl, sr) != prev:
                print('  [回合事件] 帧%d: %d:%d' % (n, sl, sr))
                rounds.append((n, sl, sr))
                prev = (sl, sr)
            if n % 2000 == 0:
                print('  [进度] %d/%d帧 (%.0fs)' % (n, rep.n_frames, time.time() - t0))
        if h:
            seed_back = struct.unpack('<I', win_probe.read_bytes(h, 0x00899D50, 4))[0]
            print('[种子回读] %d %s' % (seed_back, 'OK' if seed_back == rep.seed else 'MISMATCH'))
            win_probe.k32.CloseHandle(ctypes.c_void_p(h))
    finally:
        cli.close()

    print('\n驱动结果: %d帧 回合事件=%s 终态score=%s:%s' % (
        len(rows), rounds, rows[-1][6], rows[-1][7]))

    # 与神谕流比对
    orc = np.load(r'D:\temp\oracle_obstest0.npz')
    ox = orc['x']
    n = min(len(rows), len(ox))
    first_div = None
    for i in range(n):
        if tuple(rows[i]) != tuple(int(v) for v in ox[i]):
            first_div = i
            break
    print('神谕流 %d帧 vs 驱动 %d帧' % (len(ox), len(rows)))
    print('首个分叉帧: %s' % first_div if first_div is not None else '无分叉(逐帧一致!)')
    if first_div is not None:
        for k in range(max(0, first_div - 2), min(n, first_div + 3)):
            print('  帧%d: 驱动%s vs 神谕%s %s' % (
                k, tuple(rows[k]), tuple(int(v) for v in ox[k]),
                '<== 分叉' if k == first_div else ''))
    np.savez(r'D:\temp\drive_obstest0_oracleenv.npz',
             x=np.array(rows, dtype=np.float64), rounds=np.array(rounds))


if __name__ == '__main__':
    main()
