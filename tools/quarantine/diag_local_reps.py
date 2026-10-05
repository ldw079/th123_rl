# -*- coding: utf-8 -*-
"""对比: 用户本地原版录像 vs 钢琴男专家rep 的头部结构。"""
import os, struct, sys, glob
sys.stdout.reconfigure(encoding='utf8')

def hdr(p):
    b = open(p, 'rb').read()
    if len(b) < 125 or b[0] != 0xD2:
        return 'bad'
    return ('mode=%d @9=%02X @10-13=%s @60-62=%s @109-116=%s seed=%d 帧=%d 首=%04X/%04X' % (
        b[8], b[9],
        ' '.join('%02X' % c for c in b[10:14]),
        ' '.join('%02X' % c for c in b[60:63]),
        ' '.join('%02X' % c for c in b[109:117]),
        struct.unpack_from('<I', b, 117)[0],
        (len(b) - 121) // 4,
        *struct.unpack_from('<2H', b, 121)))

root = r'D:\touhou\hisoutensoku2026-06-15\th123\replay'
cats = [('【本地Rep】\\VS_COM', 3), ('【本地Rep】\\VS_PLAYER', 3),
        ('story', 2), ('', 2)]
for sub, n in cats:
    d = os.path.join(root, sub)
    if not os.path.isdir(d):
        print('[跳过] %s 不存在' % sub)
        continue
    files = sorted(glob.glob(os.path.join(d, '*.rep')))
    print('== %s (%d个) ==' % (sub or '(根目录)', len(files)))
    for p in files[:n]:
        print('  %-52s %s' % (os.path.basename(p)[:52], hdr(p)))

print('\n== 钢琴男专家rep对照 ==')
for p in sorted(glob.glob(r'D:\temp\expert_reps\*.rep'))[:4]:
    print('  %-52s %s' % (os.path.basename(p)[:52], hdr(p)))
