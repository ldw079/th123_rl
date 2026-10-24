# -*- coding: utf-8 -*-
"""C15(task-57 C1): ppo_gpu 熵系数/温度 env 化 — 默认等价 + env 覆盖 + meta 叠加."""
import importlib
import os
import sys
import tempfile

import numpy as np

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
os.chdir(WT)
FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


print('== ent/temp env v1 ==')
for k in ('TH123_BETA_ENT0', 'TH123_BETA_ENT_MIN', 'TH123_ENT_DECAY',
          'TH123_TEMP_INIT', 'TH123_TEMP_MIN'):
    os.environ.pop(k, None)
import ppo_gpu as G  # noqa: E402
importlib.reload(G)
T = G.PPOTrainerGPU
chk('默认 BETA_ENT_0=0.02', T.BETA_ENT_0 == 0.02)
chk('默认 BETA_ENT_MIN=0.001', T.BETA_ENT_MIN == 0.001)
chk('默认 ENT_DECAY=0.97', T.ENT_DECAY == 0.97)
chk('默认 TEMP_INIT=2.0', T.TEMP_INIT == 2.0)
chk('默认 TEMP_MIN=0.5', T.TEMP_MIN == 0.5)

os.environ['TH123_BETA_ENT_MIN'] = '0.01'
os.environ['TH123_TEMP_INIT'] = '1.5'
os.environ['TH123_TEMP_MIN'] = '0.8'
importlib.reload(G)
T = G.PPOTrainerGPU
chk('env BETA_ENT_MIN=0.01', T.BETA_ENT_MIN == 0.01)
chk('env TEMP_INIT=1.5', T.TEMP_INIT == 1.5)
chk('env TEMP_MIN=0.8', T.TEMP_MIN == 0.8)

# meta 叠加: 存档(默认值) → 带 env 载入 → 覆盖生效
os.environ.pop('TH123_BETA_ENT_MIN', None)
os.environ.pop('TH123_TEMP_INIT', None)
os.environ.pop('TH123_TEMP_MIN', None)
importlib.reload(G)
tmp = tempfile.mkdtemp(prefix='ce15_')
pi = os.path.join(tmp, 'pi.npz')
vv = os.path.join(tmp, 'v.npz')
tr = G.PPOTrainerGPU(n_side=5 * 3 + 358, n_out=3)
tr._beta = 0.0005
tr._temp = 0.6
tr._updates = 100
tr.save(pi, vv)
os.environ['TH123_BETA_ENT_MIN'] = '0.01'
os.environ['TH123_TEMP_INIT'] = '1.5'
importlib.reload(G)
tr2 = G.PPOTrainerGPU(n_side=5 * 3 + 358, n_out=3)
tr2.load(pi, vv)
chk('载入后 beta 抬到 env 下限(0.0005→0.01)', abs(tr2._beta - 0.01) < 1e-9)
chk('载入后 temp=env TEMP_INIT', abs(tr2._temp - 1.5) < 1e-9)
os.environ.pop('TH123_BETA_ENT_MIN', None)
os.environ.pop('TH123_TEMP_INIT', None)
importlib.reload(G)
tr3 = G.PPOTrainerGPU(n_side=5 * 3 + 358, n_out=3)
tr3.load(pi, vv)
chk('无 env: meta 值原样(beta=0.0005, temp=0.6)',
    abs(tr3._beta - 0.0005) < 1e-6 and abs(tr3._temp - 0.6) < 1e-6)
_src = open(os.path.join(WT, 'ppo_gpu.py'), encoding='utf8').read()
chk('生效证据日志 [ent_env] 存在', '[ent_env] effective beta=' in _src)
print('==== ent/temp env v1: %d PASS / %d FAIL ===='
      % (13 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
