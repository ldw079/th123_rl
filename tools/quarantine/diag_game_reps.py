# -*- coding: utf-8 -*-
"""检查游戏自动录制的rep(游戏目录replay/) — 头部结构对照。"""
import os, struct, sys, time
sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, r'D:\temp\soku_arch')
from soku_arch.rep_file import parse_rep_file, INPUT_START

root = r'D:\temp\soku_arch\game_extract\replay'
for fn in sorted(os.listdir(root)):
    if not fn.endswith('.rep'):
        continue
    p = os.path.join(root, fn)
    b = open(p, 'rb').read()
    st = os.stat(p)
    print('%-24s %7dB  mtime=%s' % (fn, len(b),
          time.strftime('%m-%d %H:%M', time.localtime(st.st_mtime))))
    print('  头部: %s' % ' '.join('%02X' % c for c in b[:20]))
    print('  @8 mode=%d  @14 char=%d pal=%d  @63 char=%d pal=%d  @117 seed=%d  帧=%d' % (
        b[8], b[14], b[15], b[63], b[64],
        struct.unpack_from('<I', b, 117)[0] if len(b) >= 121 else -1,
        max(0, (len(b) - 121) // 4) if len(b) >= 121 else 0))
    print('  @60-62: %s   @109-116: %s' % (
        ' '.join('%02X' % c for c in b[60:63]),
        ' '.join('%02X' % c for c in b[109:117])))
    # 首帧输入
    if len(b) >= 125:
        i0 = struct.unpack_from('<2H', b, INPUT_START)
        print('  首帧输入: %04X %04X' % i0)
