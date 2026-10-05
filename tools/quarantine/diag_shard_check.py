# -*- coding: utf-8 -*-
import numpy as np, json, sys
sys.stdout.reconfigure(encoding='utf8')
d = np.load(r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle\shards\000_52d76c15.npz',
            allow_pickle=True)
x, inp = d['x'], d['inputs']
meta = json.loads(str(d['meta']))
print('x:', x.shape, ' inputs:', inp.shape)
print('首帧:', x[0].astype(int).tolist())
print('末帧:', x[-1].astype(int).tolist())
print('输入首帧: %04X/%04X  末帧: %04X/%04X' % (inp[0][0], inp[0][1], inp[-1][0], inp[-1][1]))
print('meta:', {k: meta[k] for k in ('idx', 'char_x', 'char_y', 'seed',
                                      'n_inputs', 'frames', 'score_final',
                                      'rounds', 'err')})
