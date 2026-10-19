# -*- coding: utf-8 -*-
"""task-16: behavior_deep_report 入库工具行为测试(合成工件, 不依赖真实训练数据).

覆盖: 三表函数可跑出数值(非恒零/恒空); main() 产物 JSON/TXT 可解析.
"""
import io
import json
import os
import pickle
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='bdr_test_')
os.makedirs(os.path.join(TMP, 'frame_logs', 'reimu'), exist_ok=True)
os.makedirs(os.path.join(TMP, 'fleet', 'episodes'), exist_ok=True)
os.makedirs(os.path.join(TMP, 'actor'), exist_ok=True)
os.environ['TH123_STORE'] = TMP
os.environ['TH123_ACTOR_DIR'] = os.path.join(TMP, 'actor')
os.environ['TH123_DEEP_OUT_JSON'] = os.path.join(TMP, 'out.json')
os.environ['TH123_DEEP_OUT_TXT'] = os.path.join(TMP, 'out.txt')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.stdout.reconfigure(encoding='utf8')

from behavior_health import FL_FIELDS  # noqa: E402
import behavior_deep_report as bdr  # noqa: E402

IX = {k: i for i, k in enumerate(FL_FIELDS)}
N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    print('  PASS  %s' % name if cond else '  FAIL  %s' % name)
    if not cond:
        BAD += 1


def frame(i):
    l = [0.0] * len(FL_FIELDS)
    r = [0.0] * len(FL_FIELDS)
    l[IX['position.x']] = 400.0 + i
    l[IX['position.y']] = 0.0
    l[IX['hp']] = 10000
    l[IX['spirit']] = 2000
    l[IX['action']] = 0
    l[IX['airBorne']] = False
    l[IX['direction']] = 1.0
    r[IX['position.x']] = 700.0
    r[IX['position.y']] = 0.0
    r[IX['hp']] = 10000
    r[IX['spirit']] = 2000
    r[IX['action']] = 0
    r[IX['airBorne']] = False
    r[IX['direction']] = -1.0
    return (tuple(l), tuple(r), [])


fr = [frame(i) for i in range(80)]
dec = [(1, 0), (20, 2), (40, 3), (60, 4)]
p = os.path.join(TMP, 'frame_logs', 'reimu', 'fl_reimu_test.pkl')
pickle.dump({'frames': fr, 'decisions': dec}, io.open(p, 'wb'))

bh = {'n_dec': 100, 'cls': {'5A': 10, 'MELEE': 5},
      'follow': {'hit_atk': 3, 'hit_n': 10, 'nohit_atk': 1, 'nohit_n': 20},
      'combo': {'hit': 2, 'blocked': 1, 'dropped': 1, 'interrupted': 1},
      'trans_top': {'5A>2B': 4}}
io.open(os.path.join(TMP, 'fleet', 'episodes', 'bh_reimu_1.json'), 'w',
        encoding='utf8').write(json.dumps(bh))

al = os.path.join(TMP, 'actor', 'actor_reimu_0.log')
io.open(al, 'w', encoding='utf8').write(
    '[奖励成分] 擦弹+1.0(10帧) 规避+0.20 空挥-0.30 回报+0.50\n'
    '] 1:02:03 ep7 100决策 v3 帧1000\n')

# 三表函数
f = bdr.frame_tables('reimu')
ck(f['frames'] > 0 and f['decisions'] > 0, '表1/2: 帧日志解析出 frames/decisions')
b = bdr.bh_table('reimu')
ck(b['decisions'] == 100 and b['combo_total_bh'] == 5, '表3: BH 旁车聚合')
a = bdr.parse_actor_games('reimu')
ck(a['n_games'] == 1 and a['graze_frames_total'] == 10, 'actor 日志 graze 解析')

# main() 产物
bdr.main()
ck(os.path.exists(os.environ['TH123_DEEP_OUT_JSON']), 'main 写 JSON')
ck(os.path.exists(os.environ['TH123_DEEP_OUT_TXT']), 'main 写 TXT')
d = json.load(io.open(os.environ['TH123_DEEP_OUT_JSON'], encoding='utf8'))
ck('reimu' in d.get('chars', {}) and d['chars']['reimu']['bh']['decisions'] == 100,
   'JSON 三表结构完整')

print('\n==== task-16 behavior_deep_report: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
