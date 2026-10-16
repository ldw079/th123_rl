# -*- coding: utf-8 -*-
"""BH-4.2验证探针(bug档②): oracle回放一致性对照 — 门控前后untech
非零率 + 受击族帧上值透传一致性 + 特征位对照(修前语义=原始值)。"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

from bc_build import build_shard, mirror_frames
from feat_builder import eff_untech, HIT_ACT_IDS

shards = sorted(glob.glob(os.path.join(
    ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:12]

n_frames = 0
raw_pos = gate_pos = 0
hit_frames = 0
hit_passthrough_ok = 0
mismatch_examples = []
for sp in shards:
    try:
        meta, frames, inputs, ilog = build_shard(sp)
    except Exception:
        continue
    if ilog is None or len(frames) < 100:
        continue
    for side in (0, 1):
        if side == 0 and meta.get('char_x') is None:
            continue
        fr = frames if side == 0 else mirror_frames(frames)
        for left, right, _w, _o in fr:
            # 对手侧(right)统计
            n_frames += 1
            ru = right.get('untech', 0) or 0
            gu = eff_untech(right)
            if ru > 0:
                raw_pos += 1
            if gu > 0:
                gate_pos += 1
            if right.get('action', 0) in HIT_ACT_IDS:
                hit_frames += 1
                if ru == gu:
                    hit_passthrough_ok += 1
                elif len(mismatch_examples) < 3:
                    mismatch_examples.append((ru, gu, right.get('action')))

print('分片%d | 对手帧%d' % (len(shards), n_frames))
print('原始untech>0: %.1f%% (%d)' % (100 * raw_pos / n_frames, raw_pos))
print('门控后untech>0: %.1f%% (%d)' % (100 * gate_pos / n_frames, gate_pos))
print('受击族帧: %d, 其中门控值=原始值: %d (%.3f)'
      % (hit_frames, hit_passthrough_ok,
         hit_passthrough_ok / max(1, hit_frames)))
if mismatch_examples:
    print('!! 受击族不透传样例:', mismatch_examples)
else:
    print('受击族帧全部透传(一致性 ✓)')
print('压缩比: 门控后/原始 = %.3f (残留读数被滤除比例 %.1f%%)'
      % (gate_pos / max(1, raw_pos), 100 * (1 - gate_pos / max(1, raw_pos))))
