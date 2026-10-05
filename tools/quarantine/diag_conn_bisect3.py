# -*- coding: utf-8 -*-
"""全22模块 + 端口20983 复测连接。"""
import sys, json
sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, r'%USERPROFILE%\Desktop\workplace\th123_rl')
from diag_conn_bisect import run_case

ORIG_ML = r'D:\touhou\hisoutensoku2026-06-15\th123\ModLoaderSettings.json'
orig = json.load(open(ORIG_ML, encoding='utf-8-sig'))['modules']
OFF = ['giuroll', 'SokuAIOfflinePlayer', 'PracticeEX', 'SokuLobbiesMod',
       'IPv6MapSokuMod', 'UPnPNat']
full = []
for k, v in orig.items():
    if bool(v.get('enabled')) and not any(c.lower() in k.lower() for c in OFF):
        full.append(k)
full.append(r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll')
print('共%d模块' % len(full))
r = run_case(full, dur=50)
print('\n全22模块(20983): %s' % r)
