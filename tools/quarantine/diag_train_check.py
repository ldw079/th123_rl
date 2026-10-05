# -*- coding: utf-8 -*-
import os, time, glob, sys
sys.stdout.reconfigure(encoding='utf8')
fs = sorted(glob.glob(r'D:\temp\train_*.log'), key=os.path.getmtime, reverse=True)
for f in fs[:4]:
    print(os.path.basename(f), time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(f))))
if fs:
    print('----', os.path.basename(fs[0]), '----')
    print(open(fs[0], encoding='utf8', errors='replace').read()[-700:])
