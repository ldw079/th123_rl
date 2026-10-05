# -*- coding: utf-8 -*-
"""对半二分: 三件套+各半其余mod。"""
import sys, time
sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, r'%USERPROFILE%\Desktop\workplace\th123_rl')
from diag_conn_bisect import run_case

TRIO = [r'modules\MemoryPatch\MemoryPatch.dll',
        r'modules\ReplayDnD-old\ReplayDnD-old.dll',
        r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll']

H1 = ['ChainCFix', 'CharactersInForeground', 'ControlPnP', 'DPadFix',
      'DSoundFix', 'EasyDecks', 'FixMeiling236', 'PunishDisplay',
      'ReplayInputView', 'ReplayLabelEx']
H2 = ['SaveRep', 'ScoreTracker', 'SokuDirectXOptimizations', 'SokuReplays',
      'TrialMode', 'VolumeChanger', 'WindowResizer', 'shady-loader',
      'th123intl']

def mods_for(keys):
    out = list(TRIO)
    root = r'D:\temp\rl_game\modules'
    import os
    for k in keys:
        for d in os.listdir(root):
            if k.lower() in d.lower():
                out.append(r'modules\%s\%s.dll' % (d, d))
                break
    return out

a = run_case(mods_for(H1), dur=40)
b = run_case(mods_for(H2), dur=40)
print('\n前半(连接=%s) 后半(连接=%s)' % (a, b))
