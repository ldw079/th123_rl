# -*- coding: utf-8 -*-
"""输入流信息损失量化(纯离线): 统计rep输入流中各BattleKeys位的使用频率。
如果BandC/pause/select位使用率高，说明转换损失大；如果接近零，说明损失不是主因。
同时统计帧对齐线索：首N条输入的模式。"""
import sys, os, struct
sys.path.insert(0, '.')
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf-8')
from soku_arch.rep_file import parse_rep_file, INPUT_START

REP_DIR = r'D:\temp\soku_arch\data\rep_expert'
# 找双侧rep
ID_CHAR = {0, 1, 9}
reps = []
for dp, dns, fns in os.walk(REP_DIR):
    for fn in sorted(fns):
        if fn.endswith('.rep'):
            p = os.path.join(dp, fn)
            b = open(p, 'rb').read(70)
            if b[14] in ID_CHAR and b[63] in ID_CHAR:
                reps.append(p)
    if len(reps) >= 20:
        break

BITS = ('up', 'down', 'left', 'right', 'A', 'B', 'C', 'dash',
        'AandB', 'BandC', 'pause', 'select')
bit_counts = [0] * 12
total = 0
for p in reps[:10]:
    rep = parse_rep_file(p)
    for v in rep.inputs:
        for i in range(12):
            if v & (1 << i):
                bit_counts[i] += 1
        total += 1

print('=== BattleKeys位使用频率(%d条输入, %d个rep) ===' % (total, len(reps[:10])))
for i, name in enumerate(BITS):
    pct = 100.0 * bit_counts[i] / total if total else 0
    bar = '#' * int(pct / 2)
    print('  %-7s %8d (%5.1f%%) %s' % (name, bit_counts[i], pct, bar))

# 可映射位: up/down/left/right, A/B/C, dash, AandB→SC
# 不可映射: BandC, pause, select
loss = sum(bit_counts[9:12])
print('\n不可映射位总占比: %d/%d = %.2f%%' % (
    loss, total, 100.0 * loss / total if total else 0))

# 帧对齐线索: 首16条输入的原始值
print('\n=== 首帧模式(前8个rep的前16条) ===')
for p in reps[:8]:
    rep = parse_rep_file(p)
    head16 = rep.inputs[:16]
    print('  %s: %s' % (os.path.basename(p)[:40],
                        ' '.join('%04x' % v for v in head16)))
