# -*- coding: utf-8 -*-
"""打印rep输入流前80帧 + 转换后语义。"""
import sys, struct
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch.input_codec import BattleInput

b = open(r'D:\temp\soku_arch\game_extract\obstest0.rep', 'rb').read()
n = (len(b) - 121) // 2
ins = struct.unpack_from('<%dH' % n, b, 121)
print('总条目 %d (帧 %d)' % (n, n // 2))
for f in range(0, 80):
    a, bb = ins[2 * f], ins[2 * f + 1]
    if a or bb or f < 5:
        ba, bbr = BattleInput(a), BattleInput(bb)
        da = ba.as_dict()
        db = bbr.as_dict()
        print('帧%3d  X=%04X(d%s %s%s%s%s)  Y=%04X(d%s %s%s%s%s)' % (
            f, a, ba.direction,
            'A' if da['A'] else '', 'B' if da['B'] else '', 'C' if da['C'] else '',
            'D' if da['dash'] else '',
            bb, bbr.direction,
            'A' if db['A'] else '', 'B' if db['B'] else '', 'C' if db['C'] else '',
            'D' if db['dash'] else ''))
# X侧/Y侧首个非零输入帧
for side, idx in (('X(偶位)', 0), ('Y(奇位)', 1)):
    for f in range(n // 2):
        if ins[2 * f + idx]:
            print('%s 首个非零输入: 帧%d 值%04X' % (side, f, ins[2 * f + idx]))
            break
