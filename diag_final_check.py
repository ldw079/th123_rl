# -*- coding: utf-8 -*-
import sys, os, time
sys.stdout.reconfigure(encoding='utf8')
for f in sorted(os.listdir(r'D:\temp\th123_models')):
    if f.startswith('model_ppo_') and f.endswith('.npz') and '_v' not in f:
        mt = time.strftime('%H:%M:%S', time.localtime(
            os.path.getmtime(os.path.join(r'D:\temp\th123_models', f))))
        print('%s  %s' % (mt, f))
txt = open(r'D:\temp\train_reimu.log', encoding='utf-8',
           errors='replace').read()
lines = txt.strip().splitlines()
for l in reversed(lines):
    if '回报' in l:
        print('最新更新:', l.strip()[:120])
        break
new_errs = [l for l in lines[-30:] if '更新异常' in l]
if new_errs:
    print('新异常:', new_errs[-1][:100])
else:
    print('最近30行无更新异常 ✓')
