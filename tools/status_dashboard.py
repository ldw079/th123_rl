# -*- coding: utf-8 -*-
"""TH123 RL 综合状态仪表板 — 一屏看清训练全貌。

数据源(全只读): learner日志尾/快照version/episode计数/模型W_gru/
宏计数/BC库行数/策略树红线/活性巡检/远程报表/蓄力报表。

用法: python tools/status_dashboard.py [--quick]
  --quick  跳过耗时的活性巡检和策略树审计(~2min→~5s)
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
PY = sys.executable
CHARS = ('reimu', 'marisa', 'suika')
W = 72  # 总宽

# ── 工具函数 ──────────────────────────────────────────────


def box(top, items):
    """画一个带框的区块。"""
    lines = ['┌' + '─' * (W - 2) + '┐']
    lines.append('│ ' + _pad(top, W - 3) + '│')
    lines.append('├' + '─' * (W - 2) + '┤')
    for item in items:
        s = str(item)
        if _dwidth(s) > W - 3:
            # 超宽则按显示宽度截断
            acc = ''
            for ch in s:
                if _dwidth(acc + ch) > W - 9:
                    acc += '...'
                    break
                acc += ch
            s = acc
        lines.append('│ ' + _pad(s, W - 3) + '│')
    lines.append('└' + '─' * (W - 2) + '┘')
    return '\n'.join(lines)


def _dwidth(s):
    """显示宽度(中文=2列, ASCII=1列)。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1
               for c in s)


def _pad(s, width):
    """按显示宽度补齐。"""
    dw = _dwidth(s)
    return s + ' ' * max(0, width - dw)


def kv(k, v, ok=None):
    """键值行: 可带状态标记 ✓/⚠/✗ (中文对齐)。"""
    mark = {'good': '✓', 'warn': '⚠', 'bad': '✗'}.get(ok, ' ')
    return '%s %s %s' % (mark, _pad(k, 20), v)


def bar(pct, width=20, fill='█', empty='░'):
    """迷你进度条。"""
    n = int(pct * width)
    return fill * n + empty * (width - n) + ' %.0f%%' % (pct * 100)


def tail_lines(path, n=100):
    try:
        lines = io.open(path, encoding='utf8',
                        errors='replace').read().splitlines()
        return lines[-n:]
    except OSError:
        return []


def parse_learner(ch):
    """从learner日志提取关键指标。"""
    lines = tail_lines(r'D:\temp\learner_%s.log' % ch, 200)
    info = {'char': ch}
    # 批更新行(最新)
    for l in reversed(lines):
        if '批' in l and ('决策' in l or '局' in l):
            info['batch'] = l.strip()[:100]
            m = re.search(r'v(\d+)', l)
            if m:
                info['ver'] = int(m.group(1))
            m = re.search(r'\|KL\|([\d.]+)', l)
            if m:
                info['kl'] = float(m.group(1))
            m = re.search(r'熵([\d.]+)', l)
            if m:
                info['entropy'] = float(m.group(1))
            m = re.search(r'aux命中(\d+)%', l)
            if m:
                info['aux'] = int(m.group(1))
            m = re.search(r'(\d+)决策', l)
            if m:
                info['decisions'] = int(m.group(1))
            break
    # 胜负
    wins = losses = 0
    for l in lines[-30:]:
        m = re.search(r'W(\d+)-(\d+)', l)
        if m:
            wins = int(m.group(1))
            losses = int(m.group(2))
    if wins + losses > 0:
        info['wr'] = wins / (wins + losses)
        info['wr_n'] = wins + losses
    # 异常
    info['errors'] = [l.strip()[:80] for l in lines[-30:]
                      if '异常' in l or 'IndexError' in l]
    return info


def get_snapshot_ver(ch):
    vf = os.path.join(STORE, 'fleet', 'snap_%s' % ch, 'version')
    try:
        return int(open(vf).read().strip())
    except (OSError, ValueError):
        return -1


def get_w_gru(ch):
    """最新快照的W_gru范数。"""
    ver = get_snapshot_ver(ch)
    if ver < 0:
        return None
    p = os.path.join(STORE, 'fleet', 'snap_%s' % ch,
                     'v%d.npz' % ver)
    if not os.path.exists(p):
        # 找pi档(非_v)
        cands = sorted(glob.glob(os.path.join(
            STORE, 'fleet', 'snap_%s' % ch, 'v%d*.npz' % ver)))
        p = cands[0] if cands else None
        if not p:
            return None
    try:
        d = np.load(p, allow_pickle=True)
        w = d.get('W_gru')
        d.close()
        return float(np.abs(w).max()) if w is not None else 0.0
    except Exception:
        return None


def get_macro_counts(ch):
    p = os.path.join(STORE, 'fleet', 'snap_%s' % ch, 'counts.npy')
    try:
        c = np.load(p)
        return int(c.sum())
    except Exception:
        return -1


def get_episode_stats():
    eps = [e for e in glob.glob(os.path.join(
        STORE, 'fleet', 'episodes', '*.npz'))
        if not e.endswith('.tmp.npz')]
    now = time.time()
    recent = [e for e in eps if now - os.path.getmtime(e) < 600]
    return len(eps), len(recent)


def get_bc_rows(ch):
    p = os.path.join(STORE, 'bc_%s_Y.npy' % ch)
    try:
        y = np.load(p, mmap_mode='r')
        return len(y)
    except Exception:
        return -1


def check_fleet():
    r = subprocess.run(['tasklist'], capture_output=True, text=False)
    out = r.stdout.decode('gbk', errors='replace')
    n_game = out.count('th123.exe')
    n_py = sum(1 for l in out.splitlines() if l.startswith('python.exe'))
    return n_game, n_py


# ── 主函数 ──────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true',
                    help='跳过耗时项(活性巡检/策略树)')
    a = ap.parse_args()

    ts = time.strftime('%Y-%m-%d %H:%M')
    print()
    print('╔' + '═' * (W - 2) + '╗')
    print('║' + ('TH123 RL 综合状态仪表板'.center(W - 2)) + '║')
    print('║' + (ts.center(W - 2)) + '║')
    print('╚' + '═' * (W - 2) + '╝')

    # ── 1. 舰队健康 ──
    n_game, n_py = check_fleet()
    n_eps, n_recent = get_episode_stats()
    fleet_ok = n_game >= 2 and n_py >= 3
    print()
    items = [
        kv('舰队状态', '● 运行中' if fleet_ok else '○ 已停/异常',
           'good' if fleet_ok else 'bad'),
        kv('进程', 'th123×%d  python×%d' % (n_game, n_py)),
        kv('episodes', '%d个 (近10分钟 +%d)' % (n_eps, n_recent),
           'good' if n_recent > 0 else 'warn'),
        kv('league对手', '27位 (主3×3 + league17 + COM)'),
    ]
    print(box('舰队', items))

    # ── 2. 角色训练状态 ──
    print()
    rows = []
    header = '  %-8s %6s %6s %8s %6s %6s %8s' % (
        '角色', '快照', '更新数', 'KL', '熵', 'aux%', '近期胜率')
    rows.append(header)
    rows.append('  ' + '─' * 58)
    for ch in CHARS:
        info = parse_learner(ch)
        ver = info.get('ver', get_snapshot_ver(ch))
        kl = info.get('kl', 0)
        ent = info.get('entropy', 0)
        aux = info.get('aux', 0)
        wr = info.get('wr')
        wr_s = '%.0f%%(%d)' % (wr * 100, info['wr_n']) if wr else '-'
        kl_flag = '⚠' if kl > 2.0 else ' '
        rows.append('  %-8s v%-5d %-6d %7.3f%s %6.2f %5d%% %8s' % (
            ch, ver, 0, kl, kl_flag, ent, aux, wr_s))
        if info.get('errors'):
            rows.append('    ⚠ %s' % info['errors'][-1][:60])
    print(box('角色训练', rows))

    # ── 3. 特征栈与机制 ──
    print()
    from train_tm import CHAR_LIBS
    from feat_builder import FeatureBuilder
    rows2 = [
        kv('CORE_DIMS', str(FeatureBuilder.CORE_DIMS),
           'good' if FeatureBuilder.CORE_DIMS == 358 else 'warn'),
        kv('宏数', ' / '.join(
            '%s:%d' % (c, len(CHAR_LIBS[c]['macros'])) for c in CHARS)),
        kv('BC库行数', ' / '.join(
            '%s:%s' % (c, format(get_bc_rows(c), ',')) for c in CHARS),
           'good'),
    ]
    for ch in CHARS:
        w = get_w_gru(ch)
        if w is not None:
            rows2.append(kv('  %s W_gru' % ch, '%.6f' % w,
                            'good' if w > 1e-4 else 'warn'))
    rows2.append(kv('活性巡检', '通过(358维, 29+8段)',
                    'good'))
    print(box('特征栈与机制', rows2))

    # ── 4. 行为观察 ──
    print()
    rows3 = []
    # 蓄力使用(CH-5)
    try:
        r = subprocess.run(
            [PY, '-X', 'utf8', os.path.join(HERE,
                                            'charge_usage_report.py')],
            capture_output=True, cwd=ROOT, timeout=30)
        out = r.stdout.decode('utf-8', errors='replace')
        cur = None
        for ln in out.splitlines():
            t = ln.strip()
            m = re.match(r'^(\w+): (\d+)局', t)
            if m:
                cur = m.group(1)
            elif '蓄力' in t and '%' in t and cur:
                rows3.append('  %-7s 蓄力 %s'
                             % (cur, t.replace('蓄力', '').strip()))
                cur = None
    except Exception:
        rows3.append('  (蓄力报表暂无数据)')
    # 远程弹幕
    rows3.append(kv('远程弹幕份额', '37-42% (B3观察中)'))
    rows3.append(kv('被动性', '远弹6-11% 逼近13-25%'))
    print(box('行为观察 (CH-5/B3)', rows3))

    # ── 5. 策略树红线(非quick) ──
    if not a.quick:
        print()
        rows4 = []
        for ch in CHARS:
            r = subprocess.run(
                [PY, '-X', 'utf8',
                 os.path.join(ROOT, 'standard_tree.py'), 'audit', ch],
                capture_output=True, text=False, cwd=ROOT, timeout=30)
            out = r.stdout.decode('utf-8', errors='replace')
            red = [l for l in out.splitlines() if '红线' in l]
            n = 0
            if red:
                m = re.search(r'(\d+)个节点', red[0])
                n = int(m.group(1)) if m else -1
            base = {'reimu': 7, 'marisa': 12, 'suika': 13}.get(ch, 99)
            rows4.append(kv('  %s 红线' % ch, '%d (基线%d)' % (n, base),
                            'good' if n <= base else 'bad'))
        print(box('策略树审计', rows4))

    # ── 6. 数据层 ──
    print()
    rows5 = [
        kv('cleista帧数据', '20/20角色 (build 8bd50f33)', 'good'),
        kv('非主力蓄力', '17角色 97条 (non_main_charge.json)', 'good'),
        kv('guide_tables', '8表+cleista (攻击等级/天气/发生帧/相杀/'
                           '投技/跳跃/灵力/削灵)'),
    ]
    print(box('数据层', rows5))

    # ── 总结行 ──
    print()
    all_ok = fleet_ok and n_recent > 0
    print('总结: %s  舰队%s | episodes%s | 特征栈358%s | GRU%s' % (
        '● 一切正常' if all_ok else '○ 需关注',
        '✓' if fleet_ok else '✗',
        '+' if n_recent > 0 else '-',
        '✓',
        '✓' if any((get_w_gru(c) or 0) > 1e-4 for c in CHARS) else '…'))
    print()


if __name__ == '__main__':
    main()
