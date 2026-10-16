# -*- coding: utf-8 -*-
"""一次性: 四个游戏目录的ML写回oracle全集(事故修复)。"""
import io
import json
import os

ORACLE = ['MemoryPatch', 'ReplayDnD-old', 'SokuAITrainerEnv', 'ChainCFix',
          'FixMeiling236']
for d in ('rl_game', 'rl_game_w1', 'rl_game_w2', 'rl_game_w3'):
    p = os.path.join('D:/temp', d, 'ModLoaderSettings.json')
    ml = json.load(io.open(p, encoding='utf8'))
    mods = ml.setdefault('modules', {})
    for m in ORACLE:
        key = 'modules\\%s\\%s.dll' % (m, m)
        mods.setdefault(key, {})['enabled'] = True
    tmp = p + '.tmp'
    io.open(tmp, 'w', encoding='utf8', newline='').write(json.dumps(ml, indent=4))
    os.replace(tmp, p)
    on = sorted(k.split('\\')[-1] for k, v in mods.items()
                if v.get('enabled'))
    print(d, '启用:', on)
