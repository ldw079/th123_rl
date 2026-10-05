# -*- coding: utf-8 -*-
import os, sys, subprocess, shutil
sys.stdout.reconfigure(encoding='utf8')
store = r'D:\temp\th123_models'
for f in os.listdir(store):
    if f.startswith('model_ppo_') and f.endswith('.npz') and 'bak' not in f:
        os.remove(os.path.join(store, f))
        print('删除: %s' % f)
print('旧模型已清')
subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], capture_output=True)
subprocess.run(['taskkill', '/F', '/IM', 'th123.exe'], capture_output=True)
import time; time.sleep(3)
cache = r'%USERPROFILE%\Desktop\workplace\th123_rl\__pycache__'
if os.path.isdir(cache):
    shutil.rmtree(cache)
    print('pycache已清')
print('全部清理完毕')
