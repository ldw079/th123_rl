# -*- coding: utf-8 -*-
"""marisa弹幕诊断: B/C帧率/按压时长分布(蓄力假设) vs BC标签占比."""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')

from bc_build import build_shard   # noqa: E402

BIT_B, BIT_C = 0x20, 0x40


def main():
    press_b = press_c = total = 0
    hold_hist = []
    n_used = 0
    for sp in sorted(glob.glob(os.path.join(
            ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:80]:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if ilog is None or len(frames) < 100:
            continue
        for side in (0, 1):
            cid = meta['char_x'] if side == 0 else meta['char_y']
            if cid != 1:
                continue
            u = np.asarray(ilog[0] if side == 0 else ilog[1],
                           dtype=np.uint16)
            n_used += 1
            pb = (u & BIT_B) != 0
            pc = (u & BIT_C) != 0
            press_b += int(pb.sum())
            press_c += int(pc.sum())
            total += len(u)
            d = np.diff(pb.astype(int))
            starts = list((np.flatnonzero(d == 1) + 1).tolist())
            ends = list((np.flatnonzero(d == -1) + 1).tolist())
            if pb[0]:
                starts = [0] + starts
            if pb[-1]:
                ends = ends + [len(pb)]
            hold_hist += [int(e - s) for s, e in zip(starts, ends)]
    print('marisa侧 %d 局: B帧率%.1f%% C帧率%.1f%% (总帧%d)'
          % (n_used, press_b / max(total, 1) * 100,
             press_c / max(total, 1) * 100, total))
    if hold_hist:
        h = np.array(hold_hist)
        print('B按压%d次 中位%d帧 | ≤12帧%.0f%% 13-30帧%.0f%% '
              '>30帧(长蓄)%.0f%%'
              % (len(h), np.median(h), (h <= 12).mean() * 100,
                 ((h > 12) & (h <= 30)).mean() * 100,
                 (h > 30).mean() * 100))
        # 对照: 假设每按一次=一个弹幕决策, 决策点口径的估算
        # (总决策点≈输入变化帧数, 直接数)
        print('(按压次数口径: %.1f次/千帧)' % (len(h) / max(total, 1) * 1000))


if __name__ == '__main__':
    main()
