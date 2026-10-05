# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf8')
b = open(r'D:\temp\soku_arch\game_extract\modules\ReplayDnD\ReplayDnD.dll', 'rb').read()
print('size', len(b))
s = sorted(set(m.group(0).decode('ascii') for m in re.finditer(rb'[ -~]{5,}', b)))
out = [x for x in s if any(k in x.lower() for k in
        ('.rep', 'replay', 'argv', 'drop', 'drag', 'scene', 'logo', 'title',
         'path', 'file', '.ini', 'config', 'card', 'deck', 'watch', 'auto'))]
print(len(out), 'interesting strings:')
for x in out:
    print(repr(x))
