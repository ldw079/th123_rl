# -*- coding: utf-8 -*-
"""task-46 C15: 值头去动作条件化(默认 on; env=0 回滚; GPU/numpy 同步)."""
import importlib
import os
import sys

import numpy as np

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
os.chdir(WT)
FAIL = []
TRUNK_FLAT = 2560


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


print('== val deact (task-46) ==')
os.environ.pop('TH123_VAL_DEACT', None)   # 走默认
import mem_v1 as M  # noqa: E402
importlib.reload(M)
chk('默认 VAL_DEACT=1', bool(M.VAL_DEACT))
import torch  # noqa: E402
import ppo_gpu as G  # noqa: E402
importlib.reload(G)
n_out, n_side = 88, 5 * 88 + 382
tr = G.PPOTrainerGPU(n_side=n_side, n_out=n_out)
with torch.no_grad():   # 默认 W3v/b3v=0 → 值恒 0; 随机化才能测敏感
    tr.net.W2v.weight.normal_(0, .05)
    tr.net.W3v.normal_(0, .05)
chk('GPU net.val_deact=True', bool(tr.net.val_deact))
rng = np.random.default_rng(3)
X = torch.from_numpy(rng.normal(0, .5, (4, 3, 60, 80)).astype(np.float32))
S = torch.from_numpy(rng.normal(0, .3, (4, n_side)).astype(np.float32))
S2 = S.clone()
S2[:, :2 * n_out] = 0.0
with torch.no_grad():
    _, va, _, _ = tr.net(X, S, 1.0, None)
    _, vb, _, _ = tr.net(X, S2, 1.0, None)
chk('GPU deact: 2N 前缀不影响值',
    float((va - vb).abs().max()) < 1e-6)

os.environ['TH123_VAL_DEACT'] = '0'
importlib.reload(M)
importlib.reload(G)
tr0 = G.PPOTrainerGPU(n_side=n_side, n_out=n_out)
with torch.no_grad():
    tr0.net.W2v.weight.normal_(0, .05)
    tr0.net.W3v.normal_(0, .05)
chk('env=0 net.val_deact=False', not bool(tr0.net.val_deact))
with torch.no_grad():
    _, v0a, _, _ = tr0.net(X, S, 1.0, None)
    _, v0b, _, _ = tr0.net(X, S2, 1.0, None)
chk('env=0 旧行为: 2N 影响值',
    float((v0a - v0b).abs().max()) > 0)
os.environ['TH123_VAL_DEACT'] = '1'
importlib.reload(M)

import ppo as P  # noqa: E402
np_tr = P.PPOTrainer(n_out=n_out, n_side=n_side)
np_tr.init_fresh(TRUNK_FLAT)
rngv = np.random.default_rng(5)
np_tr.W1v = rngv.normal(0, .02, np_tr.W1v.shape).astype(np.float32)
np_tr.W2v = rngv.normal(0, .02, np_tr.W2v.shape).astype(np.float32)
np_tr.W3v = rngv.normal(0, .02, np_tr.W3v.shape).astype(np.float32)
Xn = rng.normal(0, .5, (4, TRUNK_FLAT)).astype(np.float32)
Snp = rng.normal(0, .3, (4, n_side)).astype(np.float32)
Snp2 = Snp.copy()
Snp2[:, :2 * n_out] = 0.0
os.environ['TH123_VAL_DEACT'] = '1'
_, na, _ = np_tr._v_forward(Xn, Snp)
_, nb, _ = np_tr._v_forward(Xn, Snp2)
chk('numpy deact: 2N 前缀不影响值',
    float(np.abs(na - nb).max()) < 1e-6)
os.environ['TH123_VAL_DEACT'] = '0'
_, na0, _ = np_tr._v_forward(Xn, Snp)
_, nb0, _ = np_tr._v_forward(Xn, Snp2)
chk('numpy env=0 旧行为', float(np.abs(na0 - nb0).max()) > 0)
os.environ['TH123_VAL_DEACT'] = '1'
lh = open(os.path.join(WT, 'learner_hub.py'), encoding='utf8').read()
chk('learner_hub [val] 启动行源码', '[val] deact=' in lh)
pg = open(os.path.join(WT, 'ppo_gpu.py'), encoding='utf8').read()
chk('GPU env 开关仍在(可回滚)', 'VAL_DEACT' in pg or '_VAL_DEACT' in pg)
print('==== val deact: %d PASS / %d FAIL ====' % (10 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
