# -*- coding: utf-8 -*-
"""输入配对判别实验: 用数据自证, 不猜。
方法: 对同一rep分别用swap=False和swap=True全长驱动,
统计哪种配对下重演的终局score与文件名比分的匹配率更高。
同时检验@61/@62标志位是否与正确配对相关。
"""
import sys, os, re, time, json
sys.path.insert(0, '.')
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf-8')

from soku_arch.rep_file import parse_rep_file
ID_CHAR = {0: 'reimu', 1: 'marisa', 9: 'suika'}
from soku_arch.trainer_client import (
    TrainerClient, GameEnded, TrainerError,
    OPCODE_START_GAME_VS_PLAYER)
from soku_arch.rep_file import parse_rep_file
from soku_arch.input_codec import BattleInput, battle_to_trainer
from soku_arch import win_probe
import ctypes, struct, numpy as np

REP_DIR = r'D:\temp\soku_arch\data\rep_expert'
GAME = r'D:\temp\soku_arch\game_extract'
EXE = os.path.join(GAME, 'th123.exe')
PORT_BASE = 20986
score_pat = re.compile(r'\((\d+)[︰:](\d+)_(胜|负)\)')

# 1. 收集带比分的双侧rep + 读取@61/@62标志
cands = []
for dp, dns, fns in os.walk(REP_DIR):
    for fn in sorted(fns):
        if not fn.endswith('.rep'):
            continue
        m = score_pat.search(fn)
        if not m:
            continue
        p = os.path.join(dp, fn)
        b = open(p, 'rb').read(121)
        if b[14] not in ID_CHAR or b[63] not in ID_CHAR:
            continue
        cands.append({
            'path': p, 'fn': fn,
            'fn_sl': int(m.group(1)), 'fn_sr': int(m.group(2)),
            'result': m.group(3),
            'flag61': b[61], 'flag62': b[62],
            'char_x': b[14], 'char_y': b[63],
        })
        if len(cands) >= 12:
            break
    if len(cands) >= 12:
        break

print('=== 配对判别实验 ===')
print('样本: %d个带比分双侧rep\n' % len(cands))

# 2. 统计@61/@62与胜负的关系(纯离线, 不需要游戏)
print('--- 标志位分析(离线) ---')
for c in cands[:6]:
    # 文件名胜负语义: 如果"胜"表示X(@14)赢了
    # 则fn可能是 X的得分:Y的得分 或 Y的得分:X的得分
    # 先看原始字节模式
    print('%s flag61=%d flag62=%d fn=%d:%d_%s' % (
        c['fn'][:50], c['flag61'], c['flag62'],
        c['fn_sl'], c['fn_sr'], c['result']))

# 统计: 胜/负 与 flag61/62的关联
from collections import Counter
win_61 = Counter()
lose_61 = Counter()
for c in cands:
    if c['result'] == '胜':
        win_61[c['flag61']] += 1
    else:
        lose_61[c['flag61']] += 1
print('\n胜→flag61分布:', dict(win_61))
print('负→flag61分布:', dict(lose_61))

# 3. 驱动实验: 每个rep跑两种配对, 比较score
results = []
for idx, c in enumerate(cands[:6]):
    rep = parse_rep_file(c['path'])
    for swap in (False, True):
        port = PORT_BASE + idx * 2 + (1 if swap else 0)
        tag = 'swap=True' if swap else 'swap=False'
        print('\n[%d/%d] %s %s' % (idx + 1, min(6, len(cands)),
                                   c['fn'][:45], tag))
        cli = TrainerClient(port, EXE, GAME, launch=True,
                            env={'SOKUAI_PORT': str(port),
                                 'SOKUAI_SEED': str(rep.seed)})
        drv_sl, drv_sr = -1, -1
        try:
            cli.handshake()
            hwnd = win_probe.find_window(cli.proc.pid)
            if hwnd:
                win_probe.force_foreground(hwnd)
            h = win_probe.open_for_write(cli.proc.pid)
            if h:
                if win_probe.read_bytes(h, win_probe.TBL_ADDR, 8) != \
                        struct.pack('<II', win_probe.MGR_ADDR,
                                   win_probe.MGR_ADDR):
                    win_probe.write_bytes(
                        h, win_probe.TBL_ADDR,
                        struct.pack('<II', win_probe.MGR_ADDR,
                                   win_probe.MGR_ADDR))
            cli.wait_for_ready(max_wait=30.0)
            first = cli.start_game(
                rep.char_x, rep.char_y,
                left_deck=list(rep.deck_x),
                right_deck=list(rep.deck_y),
                left_palette=rep.pal_x, right_palette=rep.pal_y,
                opcode=OPCODE_START_GAME_VS_PLAYER, hook=lambda: None)
            timeouts = 0
            for f, a, b in rep.frames():
                if cli.proc and cli.proc.poll() is not None:
                    break
                la, ra = (b, a) if swap else (a, b)
                li, _ = battle_to_trainer(BattleInput(la))
                ri, _ = battle_to_trainer(BattleInput(ra))
                try:
                    cli.send_inputs(li.as_dict(), ri.as_dict())
                    kind, payload = cli.poll(timeout=3.0)
                    if kind == 'fault':
                        break
                    if kind == 'ended':
                        drv_sl, drv_sr = payload[1], payload[2]
                        break
                    if kind == 'error':
                        if payload in (12, 17):
                            continue
                        break
                except TimeoutError:
                    timeouts += 1
                    if timeouts > 30:
                        break
                    continue
            if drv_sl < 0:
                # 流尽: 取最后观测的score
                if kind == 'frame' or True:
                    try:
                        drv_sl = payload['left']['score']
                        drv_sr = payload['right']['score']
                    except Exception:
                        pass
            if h:
                win_probe.k32.CloseHandle(ctypes.c_void_p(h))
        except Exception as e:
            print('  异常: %s %s' % (type(e).__name__, str(e)[:60]))
        finally:
            cli.close()
        # 比对(尝试两种语义: 左:右 和 右:左)
        m_lr = (drv_sl == c['fn_sl'] and drv_sr == c['fn_sr'])
        m_rl = (drv_sl == c['fn_sr'] and drv_sr == c['fn_sl'])
        print('  驱动=%d:%d 文件名=%d:%d → %s%s' % (
            drv_sl, drv_sr, c['fn_sl'], c['fn_sr'],
            'LR一致' if m_lr else '', 'RL一致' if m_rl else ''))
        results.append({
            'swap': swap, 'drv_sl': drv_sl, 'drv_sr': drv_sr,
            'fn_sl': c['fn_sl'], 'fn_sr': c['fn_sr'],
            'm_lr': m_lr, 'm_rl': m_rl,
            'flag61': c['flag61'], 'result': c['result'],
        })
        time.sleep(2)

# 4. 统计汇总
print('\n=== 汇总 ===')
for swap in (False, True):
    tag = 'swap=True' if swap else 'swap=False'
    sub = [r for r in results if r['swap'] == swap and r['drv_sl'] >= 0]
    lr = sum(1 for r in sub if r['m_lr'])
    rl = sum(1 for r in sub if r['m_rl'])
    n = len(sub)
    print('%s: 可判%d LR匹配%d RL匹配%d' % (tag, n, lr, rl))
