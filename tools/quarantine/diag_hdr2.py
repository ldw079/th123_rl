# -*- coding: utf-8 -*-
"""深挖 rep 头部 @109-116: 相关性分析。"""
import os, struct, collections

root = r'D:\temp\expert_reps'
rows = []
for dp, _, fs in os.walk(root):
    for fn in fs:
        if not fn.lower().endswith('.rep'):
            continue
        p = os.path.join(dp, fn)
        b = open(p, 'rb').read()
        if len(b) < 121 or b[0] != 0xD2:
            continue
        n_frames = (len(b) - 121) // 4
        u32_113 = struct.unpack_from('<I', b, 113)[0]
        u16_113 = struct.unpack_from('<H', b, 113)[0]
        rows.append((fn, b[8], len(b), n_frames, b[109], b[110], b[111], b[112],
                     u16_113, u32_113))

# 1) @113 u16 与 n_frames 的相关性(粗查: 分布对照)
print('== u16@113 分位数 vs n_frames ==')
import statistics
vals = sorted((r[8], r[3]) for r in rows)
n = len(vals)
for q in (0, 10, 25, 50, 75, 90, 100):
    idx = min(n - 1, q * (n - 1) // 100)
    print('  p%3d: u16@113=%5d  n_frames=%6d' % (q, vals[idx][0], vals[idx][1]))

# 2) mode 与 off9 / off61 / off110 / off111 / off112 的交叉
print('\n== mode x (off9, off61, off110, off111, off112) ==')
cross = collections.Counter()
for r in rows:
    cross[(r[1], r[4], r[5], r[6], r[7], r[8])] += 1
for k, c in sorted(cross.items(), key=lambda x: -x[1])[:12]:
    print('  mode=%d off9=%02X off61=%d off110=%d off111=%d off112=%d -> %d' % (
        k[0], k[1], k[2], k[3], k[4], k[5], c))

# 3) u32@113 是否均匀(像随机数) —— 与 seed 对比熵
print('\n== u32@113 样本 ==')
for r in rows[:10]:
    print('  %s mode=%d u32@113=%u(0x%08X) seed待查' % (
        r[0][:40], r[1], r[9], r[9]))

# 4) 检查 u16@113 与 n_frames 的比值是否像"秒数"
print('\n== u16@113 / (n_frames/62) 即"如果@113是秒, 每秒帧数" ==')
ratios = []
for r in rows:
    if r[3] > 100 and r[8] > 0:
        ratios.append(r[3] / r[8])
ratios.sort()
n = len(ratios)
for q in (0, 25, 50, 75, 100):
    idx = min(n - 1, q * (n - 1) // 100)
    print('  p%3d: frames_per_unit=%.2f' % (q, ratios[idx]))
