# -*- coding: utf-8 -*-
import sys, collections
sys.path.insert(0, r'%USERPROFILE%\Desktop\workplace\th123_rl')
sys.stdout.reconfigure(encoding='utf8')
from oracle_batch import bilateral_reps
files = bilateral_reps()
print('双边rep总数:', len(files))
c = collections.Counter()
for fn, p in files:
    b = open(p, 'rb').read(65)
    c[(b[14], b[63])] += 1
names = {0: '灵梦', 1: '魔理沙', 9: '萃香'}
for (x, y), n in sorted(c.items()):
    print('  %s(%d) vs %s(%d): %d局' % (names.get(x, x), x, names.get(y, y), y, n))
