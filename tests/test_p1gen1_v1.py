# -*- coding: utf-8 -*-
"""Gen-1 单测(hermetic, task-40): mem 编码/ep v3 hist/迁移等价/一步学习/批 k4 env.

不读 live store: 迁移 fixture 由 env=0 trainer 在本测试 temp 目录内合成.
"""
import importlib
import json
import os
import shutil
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


print('== Gen-1 ==')
# 1) mem_v1 编码
os.environ['TH123_MEM_DECISIONS'] = '8'
import mem_v1 as M  # noqa: E402
chk('mem env=8', M.MEM_DECISIONS == 8 and M.HIST_DIM == 24 and M.MEM_IN == 27)
chk('hist_step 布局', M.hist_step(350, 1, 350, 0) == (0, 1, 12))
chk('opp_events startup', M.opp_events(350, 0) & 8)
chk('opp_events untech', M.opp_events(0, 5) & 64)
chk('flatten_hist 形状', M.flatten_hist(np.zeros((4, 8, 3), np.int8)).shape
    == (4, 24))
chk('zeros_mem_input 形状', M.zeros_mem_input(3).shape == (3, 27))
_wh = M.window_hist([M.hist_step(350, 1, 0, 0)], 8)
chk('window_hist (8,3) 左补零', _wh.shape == (8, 3)
    and int(_wh[-1][0]) == 0 and int(_wh[0].sum()) == 0)

# 2) episode schema v3 hist roundtrip + v2 兼容
import episode_core as E  # noqa: E402
N, n_side, n_macros = 6, 5 * 88 + 382, 88
tmp = tempfile.mkdtemp(prefix='gen1_ep_')
arrs = dict(
    feats=np.zeros((N, E.FEAT_DIMS), np.uint8),
    sides=np.zeros((N, n_side), np.float32),
    acts=np.arange(N, dtype=np.int64) % n_macros,
    rews=np.zeros(N, np.float32),
    masks=np.ones((N, n_macros), bool),
    bc_targets=np.zeros(N, np.int64),
    opp_next=np.zeros(N, np.int64),
    logps=np.zeros(N, np.float32),
    ep_terms=np.array([True]),
    distill=np.zeros((0, 11), np.float32),
    hist=np.random.default_rng(1).integers(0, 120, (N, 8, 3), dtype=np.int8),
)
contract = E.build_contract('reimu', n_macros, n_side, n_macros, E.FEAT_DIMS)
contract['mem_dim'] = 8
meta = {'char': 'reimu', 'actor': 0, 'ep': 1, 'contract': contract}
p = E.save_episode_npz(tmp, 'reimu', 0, 1, arrs, json.dumps(meta))
arr2, _ = E.load_episode_npz(p)
chk('ep v3 schema', int(np.load(p)['schema']) == 3)
chk('ep v3 hist roundtrip', np.array_equal(arr2['hist'], arrs['hist']))
arrs2 = dict(arrs)
arrs2.pop('hist')
p2 = E.save_episode_npz(tmp, 'reimu', 1, 1, arrs2,
                        json.dumps({**meta, 'actor': 1}))
arr3, _ = E.load_episode_npz(p2)
chk('ep v2 兼容(hist=None)', int(np.load(p2)['schema']) == 2
    and arr3['hist'] is None)
shutil.rmtree(tmp, ignore_errors=True)

# 3) 批 env/k4 env 源码锚
_lh = open(os.path.join(WT, 'learner_hub.py'), encoding='utf8').read()
chk('批 env 常量', "TH123_BATCH_MIN_GAMES" in _lh
    and "TH123_BATCH_MIN_DECISIONS" in _lh
    and "TH123_BATCH_WAIT_MAX" in _lh and "[batch] timeout" in _lh)
_fb = open(os.path.join(WT, 'feat_builder.py'), encoding='utf8').read()
chk('k4 env 常量', "TH123_K4_URGENCY" in _fb and "corner_urgency" in _fb)

# 4) hermetic 迁移 fixture: env=0 trainer 合成旧档 → 迁移 → 等价/敏感性/一步学习
os.environ['TH123_MEM_DECISIONS'] = '0'
importlib.reload(M)
import torch  # noqa: E402
import ppo_gpu as G  # noqa: E402
n_out = 88
n_side = 5 * n_out + 382
tmp2 = tempfile.mkdtemp(prefix='gen1_h_')
pi = os.path.join(tmp2, 'model_ppo_reimu_fleet.npz')
vv = os.path.join(tmp2, 'model_ppo_reimu_fleet_v.npz')
tr0 = G.PPOTrainerGPU(n_side=n_side, n_out=n_out)
tr0.save(pi, vv)
tr0.net.cpu().double().eval()
rng = np.random.default_rng(7)
X = torch.from_numpy(rng.normal(0, .5, (4, 3, 60, 80)))
S = torch.from_numpy(rng.normal(0, .3, (4, n_side)))
with torch.no_grad():
    z_old = tr0.net(X, S, 1.0, None)[0].clone()

sys.path.insert(0, os.path.join(WT, 'tools'))
import importlib as _il  # noqa: E402
_mig = _il.import_module('migrate_p1gen1')
_mig.migrate_one(pi, vv, n_out, dry=False)
d = np.load(pi)
chk('迁移档无 Wf 键 + 有 mem_dim/W_mem',
    'Wf1' not in d.files and 'mem_dim' in d.files and 'W_mem' in d.files)
chk('迁移后 W_mem 全零(加性零初始化)', float(np.abs(d['W_mem']).max()) == 0.0)
chk('迁移后 mem_fc2 非零(打破死分支)',
    float(np.abs(d['mem_fc2']).max()) > 0.0)
chk('备份 *_pre_p1gen1.npz',
    os.path.exists(os.path.join(tmp2,
                                'model_ppo_reimu_fleet_pre_p1gen1.npz')))
importlib.reload(M)
importlib.reload(G)
tr1 = G.PPOTrainerGPU(n_side=n_side, n_out=n_out)
tr1.load(pi, vv)
tr1.net.cpu().double().eval()
with torch.no_grad():
    z_env0 = tr1.net(X, S, 1.0, None)[0]
chk('env=0 迁移档 maxdiff=0.0',
    float((z_old - z_env0).abs().max()) < 1e-9)

os.environ['TH123_MEM_DECISIONS'] = '8'
importlib.reload(M)
importlib.reload(G)
tr8 = G.PPOTrainerGPU(n_side=n_side, n_out=n_out)
tr8.load(pi, vv)
tr8.net.double()
H1 = torch.zeros(4, 27, dtype=torch.float64)
H2 = torch.zeros(4, 27, dtype=torch.float64)
H2[:, 0] = 1.0
tr8.net.train()
tr8.net.zero_grad()
Hr = torch.from_numpy(rng.normal(0, 1.0, (4, 27))).double()
out = tr8.net(X, S, 1.0, None, H=Hr)
loss = (out[0] ** 2).sum()
loss.backward()
g = tr8.net.W_mem.weight.grad
chk('W_mem 梯度非零(死分支修复)', g is not None
    and float(g.detach().abs().max()) > 0.0)
with torch.no_grad():
    tr8.net.W_mem.weight.copy_(tr8.net.W_mem.weight - 1e-3 * g)
chk('一步后 W_mem.absmax>0(实际学习)',
    float(tr8.net.W_mem.weight.detach().abs().max()) > 0.0)
# 零初始化 W_mem 下 H 扰动必然无差, 故在一步更新后验证敏感性>0
with torch.no_grad():
    za = tr8.net(X, S, 1.0, None, H=H1)[0]
    zb = tr8.net(X, S, 1.0, None, H=H2)[0]
chk('env=8 hist 敏感性 >0(更新后)', float((za - zb).abs().max()) > 1e-9)
# 5) 真实 update() 路径: W_mem 必须学到非零(端到端, 防"H 漏传"再回归)
tr8.net.float()
Ntr = 24
rng4 = np.random.default_rng(4)
feats_tr = rng4.integers(0, 255, (Ntr, 3, 60, 80), dtype=np.uint8)
sides_tr = np.zeros((Ntr, n_side), np.float32)
acts_tr = np.zeros(Ntr, np.int64)
rews_tr = np.zeros(Ntr, np.float32)
hist_tr = rng4.integers(0, 120, (Ntr, 8, 3), dtype=np.int8)
tr8.update(feats_tr, acts_tr, rews_tr, sides_tr, [Ntr],
           ep_terms=[True], hist=hist_tr)
chk('update() 真实路径后 W_mem.absmax>0(端到端学习)',
    float(tr8.net.W_mem.weight.detach().abs().max()) > 0)
shutil.rmtree(tmp2, ignore_errors=True)
print('==== Gen-1: %d PASS / %d FAIL ====' % (25 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
