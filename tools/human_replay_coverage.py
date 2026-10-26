# -*- coding: utf-8 -*-
"""task-70 v0: 人类回放可复现性（只读）.

解析 mian 1743 .rep（soku_arch.rep_file）→ 逐帧输入 → 对照动作接口 v0
（宏 slot + 残差 v0: 方向 5 类 / A / B / 持续档 1,2,4,6,8F）计算：
  单帧可表达率、时序可复现率(档位可分解)、缺口分类（C/dash/对角/组合键/时长档）。
输出 JSON + 摘要；不改任何文件（只读 .rep）。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')

from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa: E402

BITS = ('up', 'down', 'left', 'right', 'A', 'B', 'C', 'dash')
DIRS = {(0, 0): 5, (0, -1): 8, (0, 1): 2, (-1, 0): 4, (1, 0): 6,
        (-1, -1): 7, (1, -1): 9, (-1, 1): 1, (1, 1): 3}
DIR_CLASS5 = {5, 8, 2, 4, 6}          # neutral/up/down/left/right
ALLOWED_DUR = (1, 2, 4, 6, 8)


def decode(raw):
    bits = {n: bool((raw >> i) & 1) for i, n in enumerate(BITS)}
    dx = int(bits['right']) - int(bits['left'])
    dy = int(bits['down']) - int(bits['up'])
    return bits, (dx, dy)


def can_express_frame(bits, dirv):
    """残差 v0 单帧可表达: 无 C/dash, 方向∈5 类, 按钮⊆{A,B}."""
    if bits['C'] or bits['dash']:
        return False
    if DIRS.get(dirv, 0) not in DIR_CLASS5:
        return False
    return True


def decompose(n, max_seg=3):
    """长度 n 用允许档位分解，返回最少段数（>max_seg 视为不可复现）。"""
    if n <= 0:
        return 0
    for k in range(1, max_seg + 1):
        # DFS 组合
        def dfs(rem, kk):
            if rem == 0:
                return True
            if kk == 0:
                return False
            for d in ALLOWED_DUR:
                if d <= rem and dfs(rem - d, kk - 1):
                    return True
            return False
        if dfs(n, k):
            return k
    return 10 ** 6


def target_side(fname):
    """文件名 "A-char vs B-char" → 目标 mian 侧(0=左,1=右)."""
    low = os.path.basename(fname).lower()
    parts = low.split(' vs ')
    if len(parts) != 2:
        return 1
    return 0 if 'mian' in parts[0] else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default="D:\\TR丹尼尔棉咖啡等录像精选"
                                    "\\国内\\【置顶】mian（国内）（神）")
    ap.add_argument('--limit', type=int, default=50)
    ap.add_argument('--out', default=r'D:\temp\scratch\human_replay_coverage_v0.json')
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, '**', '*.rep'),
                             recursive=True))
    files = files[:a.limit] if a.limit > 0 else files
    agg = {'files': 0, 'frames': 0, 'expressible': 0, 'gap_C': 0,
           'gap_dash': 0, 'gap_diag': 0, 'gap_both_AB': 0,
           'gap_dir_other': 0, 'transitions': 0, 'runs': 0,
           'runs_dur_ok': 0, 'runs_unreproducible': 0, 'dir_hist': {},
           'dur_hist': {}, 'per_file': []}
    for p in files:
        try:
            rep = parse_rep_file(p)
            arr = inputs_by_side(list(rep.inputs))
        except Exception as e:
            continue
        side = target_side(p)
        seq = arr[:, side]
        prev = None
        run_len = 0
        file_ok = 0
        for raw in seq:
            raw = int(raw)
            bits, dirv = decode(raw)
            agg['frames'] += 1
            if can_express_frame(bits, dirv):
                agg['expressible'] += 1
                file_ok += 1
            if bits['C'] and not bits['A'] and not bits['B']:
                agg['gap_C'] += 1
            if bits['dash']:
                agg['gap_dash'] += 1
            if DIRS.get(dirv, 0) not in DIR_CLASS5:
                agg['gap_diag'] += 1
            if bits['A'] and bits['B']:
                agg['gap_both_AB'] += 1
            agg['dir_hist'][str(DIRS.get(dirv, 0))] = \
                agg['dir_hist'].get(str(DIRS.get(dirv, 0)), 0) + 1
            key = (raw,)
            if prev == key:
                run_len += 1
            else:
                if prev is not None:
                    agg['runs'] += 1
                    agg['dur_hist'][str(run_len)] = \
                        agg['dur_hist'].get(str(run_len), 0) + 1
                    if decompose(run_len) <= 3:
                        agg['runs_dur_ok'] += 1
                    else:
                        agg['runs_unreproducible'] += 1
                agg['transitions'] += 1
                prev, run_len = key, 1
        agg['files'] += 1
        agg['per_file'].append({
            'file': os.path.basename(p), 'frames': int(len(seq)),
            'expressible': int(file_ok),
            'rate': round(file_ok / max(1, len(seq)), 3)})
    agg['single_frame_expressible_rate'] = round(
        agg['expressible'] / max(1, agg['frames']), 4)
    agg['timing_reproducible_rate'] = round(
        agg['runs_dur_ok'] / max(1, agg['runs']), 4)
    agg['note'] = ('v0 口径: 单帧可表达=无C/dash+方向5类+按钮⊆{A,B}; '
                   '时序可复现=同输入 run 用 {1,2,4,6,8}F ≤3 段分解; '
                   '对角/8向在 v0 5类下记缺口。')
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(agg, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: agg[k] for k in (
        'files', 'frames', 'single_frame_expressible_rate',
        'timing_reproducible_rate', 'gap_C', 'gap_dash', 'gap_diag',
        'gap_both_AB', 'transitions', 'runs')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
