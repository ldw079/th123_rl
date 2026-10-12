# -*- coding: utf-8 -*-
"""B2(未决问题方案§B, 用户裁定③自任测量员): 顶端标尺 — 真人 vs 模型最小协议.

mod P2-only 编译路线受阻(build_tm.bat 依赖的 D:/VS 工具链 2026-10-11晚被
清理, 仅剩残壳) → 走方案预批的**应急回退**: 客户端 GetAsyncKeyState 轮询
人类键盘, 转发为 P1 输入(无需重编 mod)。

HumanMatchEnv(tm_env 子类, B2-2):
  - tps=60(与人类同速 — 模型无超速反应优势, 公平性并入R1红线延伸);
  - P1 输入 = 物理键盘轮询(默认布局 WASD+J/K/L/O/U, config.py KEYMAP同源);
  - P2 = SideDriver(模型); TCP 锁步协议照常(P1 输入由我们转发=合法己方);
  - 每局结束自动归档 rep 文件路径到 json(取证+复核);
  - 会话统计: 逐场比分/系列比分(BO-N)。

测量协议(B2-3 首测简化版): 单场或 BO3/BO5 起步(完整 BO15 待系列方案
阶段1 SeriesManager); 用户为固定测量员(裁定③)。

用法:
  python tools/human_match.py --char reimu --bo 3     # BO3 vs 模型
  (启动后游戏窗口需前台; ESC 之外的键全部经轮询转发)
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

from side_driver import EvalEnv

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
REPORT = os.path.join(HERE, 'human_match_report.json')

user32 = ctypes.windll.user32
GetAsyncKeyState = user32.GetAsyncKeyState

# config.py KEYMAP 同源(方案B2-2: 键位与整合包默认一致) — VK 码表
VK = {'W': 0x57, 'A': 0x41, 'S': 0x53, 'D': 0x44,
      'J': 0x4A, 'K': 0x4B, 'L': 0x4C, 'O': 0x4F, 'U': 0x55}

# 轮询→协议输入位(与 soku_client2/TCP 协议的键名对齐)
_KEYMAP = {
    'W': 'up', 'S': 'down', 'A': 'left', 'D': 'right',
    'J': 'A', 'K': 'B', 'L': 'C', 'O': 'D', 'U': 'SW',
}


def poll_human_input():
    """GetAsyncKeyState 轮询 → 协议输入 dict(方案预批应急路线)."""
    inp = {}
    for key, name in _KEYMAP.items():
        if GetAsyncKeyState(VK[key]) & 0x8000:
            inp[name] = True
    return inp


def run_match(char, bo=3, port=None, seed_note='', mode='mod'):
    """一场 BO-N: 人类P1 vs 模型P2(SideDriver). mode: mod=新mod P2-only
    正路(SOKUAI_P2_ONLY=1, 物理键盘直通, 客户端P1发{}) / poll=轮询应急."""
    from side_driver import SideDriver
    port = port or 20975   # probe段低频口(人测会话级, 不与训练冲突)
    opp = SideDriver(char, 'R')
    opp.load(os.path.join(STORE, 'model_ppo_%s.npz' % char))

    _restore_env = None
    if mode == 'mod':
        _restore_env = os.environ.get('SOKUAI_P2_ONLY')
        os.environ['SOKUAI_P2_ONLY'] = '1'
    try:
        env = EvalEnv(port, char_left=char, char_right=char,
                      vs_com=False, tps=60)  # 60tps=同速公平(B2-2)
    finally:
        if mode == 'mod':
            if _restore_env is None:
                os.environ.pop('SOKUAI_P2_ONLY', None)
            else:
                os.environ['SOKUAI_P2_ONLY'] = _restore_env
    human_w = model_w = 0
    games = []
    print('[human-match] 窗口置前后开始; 键位 W/A/S/D+J(A)/K(B)/L(C)/'
          'O(D)/U(符卡); 每场BO3小局')
    # I(未决方案§I): 动作序列累积 — 供habit_detector会话后习惯报告
    # (游戏态resolved action/灵力, 非键盘推断 — 语义正确源)
    action_seq = []
    try:
        while human_w < bo and model_w < bo:
            t0 = time.time()
            frames = 0
            _opp_inp = {}
            while True:
                inp1 = {} if mode == 'mod' else poll_human_input()
                r = env.step(inp1, _opp_inp)
                frames += 1
                if env.last_match:
                    _w, ls, rs = env.last_match
                    env.last_match = None
                    if ls > rs:
                        human_w += 1
                    else:
                        model_w += 1
                    games.append({'human': ls, 'model': rs,
                                  'frames': frames,
                                  'wall_s': round(time.time() - t0, 1)})
                    print('[human-match] 场终 %d-%d (系列 %d-%d) %.0fs'
                          % (ls, rs, human_w, model_w,
                             time.time() - t0))
                    break
                if r is None:
                    break
                left, right, weather, objs = r
                action_seq.append((frames, left.get('action', 0),
                                   left.get('spirit', 0),
                                   right.get('action', 0)))
                # SideDriver P2同构: own=right(P2视角), opp=left
                _opp_inp = opp.frame_input(right, left, weather, objs, [])
    finally:
        try:
            env.close()
        except Exception:
            pass
    # I: 习惯报告(habit_detector消费真人动作流 — 教学产品化第一半)
    habit_txt = ''
    habits_out = []
    try:
        from habit_detector import detect_habits, habit_report
        habits = detect_habits(action_seq) if action_seq else []
        habits_out = habits
        habit_txt = habit_report(habits, char)
        print()
        print(habit_txt)
    except Exception as e:
        print('[human-match] 习惯报告异常(%s) — 对局结果不受影响' % e)
    return {'char': char, 'bo': bo, 'human_wins': human_w,
            'model_wins': model_w, 'games': games,
            'n_frames_obs': len(action_seq),
            'habits': [k for k, _h, _r in habits_out],
            'habit_report': habit_txt,
            'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
            'note': seed_note,
            'protocol': ('mod P2-only(SOKUAI_P2_ONLY)' if mode == 'mod'
                 else 'GetAsyncKeyState轮询(应急路线)')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--bo', type=int, default=3,
                    help='BO-N(N胜制: 先到N场胜)')
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--mode', choices=['mod', 'poll'], default='mod',
                    help='mod=P2-only正路 / poll=键盘轮询应急')
    ap.add_argument('--note', default='')
    args = ap.parse_args()
    rep = run_match(args.char, args.bo, args.port, args.note, args.mode)
    print('\n[human-match] 终局: 人类 %d - %d 模型 (%s)'
          % (rep['human_wins'], rep['model_wins'], rep['char']))
    old = []
    if os.path.exists(REPORT):
        try:
            old = json.load(open(REPORT, encoding='utf8'))
        except (OSError, ValueError):
            old = []
    old.append(rep)
    tmp = REPORT + '.tmp'
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(old[-50:], f, ensure_ascii=False, indent=1)
    os.replace(tmp, REPORT)
    print('报告追加:', REPORT)


if __name__ == '__main__':
    main()
