# -*- coding: utf-8 -*-
"""与模型对战 — 角色选择菜单(中文由Python输出, 规避bat编码问题)。

用法: python tools/human_match_menu.py
      (或双击 人测对战.bat)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

PY = sys.executable
STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
W = 56
TRAINED = ('reimu', 'marisa', 'suika')
CN = {'reimu': '灵梦', 'marisa': '魔理沙', 'suika': '萃香', 'sakuya': '咲夜',
      'alice': '爱丽丝', 'patchouli': '帕秋莉', 'youmu': '妖梦',
      'remilia': '蕾米莉亚', 'yuyuko': '幽幽子', 'reisen': '铃仙',
      'komachi': '小町', 'iku': '衣玖', 'tenshi': '天子', 'sanae': '早苗',
      'cirno': '琪露诺', 'meiling': '美铃', 'utsuho': '空',
      'suwako': '诹访子', 'yukari': '紫', 'aya': '文'}


def _dwidth(s):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1
               for c in s)


def _pad(s, w):
    return s + ' ' * max(0, w - _dwidth(s))


def box(title, lines, w=W):
    out = ['╔' + '═' * (w - 2) + '╗',
           '║ ' + _pad(title, w - 4) + ' ║',
           '╠' + '═' * (w - 2) + '╣']
    for l in lines:
        out.append('║ ' + _pad(l, w - 4) + ' ║')
    out.append('╚' + '═' * (w - 2) + '╝')
    return '\n'.join(out)


def model_ok(ch):
    p = os.path.join(STORE, 'model_ppo_%s.npz' % ch)
    if not os.path.exists(p):
        return None
    try:
        import numpy as np
        d = np.load(p)
        n = int(d['W2'].shape[1])
        d.close()
        return n
    except Exception:
        return None


def pick_char():
    """返回角色名 或 None(取消)。"""
    order = list(TRAINED) + [c for c in sorted(CN) if c not in TRAINED]
    while True:
        print()
        lines = []
        for i, ch in enumerate(order, 1):
            n = model_ok(ch)
            if n is None:
                tag = '无模型'
            elif ch in TRAINED:
                tag = '训练中 [%d宏] 强烈推荐' % n
            else:
                tag = '未训练 [%d宏] 很弱' % n
            lines.append('  [%2d] %s %s %s'
                         % (i, _pad(ch, 9),
                            _pad(CN.get(ch, '?'), 8), tag))
        lines.append('')
        lines.append('  [ 0] 取消')
        print(box('与模型对战 — 选择 AI 角色', lines))
        try:
            c = input('\n  选择 [0-%d]: ' % len(order)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if c == '0':
            return None
        if c.isdigit() and 1 <= int(c) <= len(order):
            ch = order[int(c) - 1]
            if model_ok(ch) is None:
                print('\n  !! %s 无模型档, 请换一个' % ch)
                continue
            return ch
        print('\n  ? 无效选择')


def main():
    ch = pick_char()
    if ch is None:
        return 0
    print()
    print(box('准备对战: %s (%s)' % (ch, CN.get(ch, '?')), [
        '',
        '  请在游戏里操作:',
        '    1. 启动原版游戏 (th123\\th123.exe)',
        '    2. 进入 VS PLAYER',
        '    3. P2 选择 "RL-AI"',
        '    4. 进对局后自动接管 P2',
        '',
        '  时长: 不限 (想打多久打多久)',
        '  结束: 在窗口按 Ctrl+C → 自动出报告',
        '',
    ]))
    print('\n  3 秒后启动 runner (可 Ctrl+C 取消)...')
    try:
        import time
        for i in range(3, 0, -1):
            print('    %d...' % i, end='\r', flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n  已取消')
        return 0
    print('\n')
    return subprocess.run(
        [PY, '-X', 'utf8',
         os.path.join(HERE, 'human_match_v2.py'),
         '--char', ch, '--seconds', '0'], cwd=ROOT).returncode


if __name__ == '__main__':
    sys.exit(main())
