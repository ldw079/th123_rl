# -*- coding: utf-8 -*-
"""task-50 C15: Gen-2 A 迁移工具(5N+CORE 布局) + CORE_DIMS 闸门."""
import importlib
import os
import sys

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


print('== gen2 A v1 ==')
os.environ.pop('TH123_GEN2', None)
import feat_builder as F  # noqa: E402
importlib.reload(F)
chk('默认 CORE=382', F.FeatureBuilder.CORE_DIMS == 382)
os.environ['TH123_GEN2'] = '1'
importlib.reload(F)
chk('GEN2=1 CORE=391', F.FeatureBuilder.CORE_DIMS == 391)
os.environ['TH123_GEN2'] = '0'
importlib.reload(F)

sys.path.insert(0, os.path.join(WT, 'tools'))
import migrate_gen2 as G  # noqa: E402
importlib.reload(G)
n_out, trunk, opp = 3, 7, 16
old_side = 5 * n_out + 382          # =397
d = {
    'W_side': np.arange(old_side * n_out, dtype=np.float32)
    .reshape(old_side, n_out),
    'Ws1.weight': np.arange(old_side * 5, dtype=np.float32)
    .reshape(old_side, 5),
    'W1v': np.arange((trunk + old_side + opp) * 6, dtype=np.float32)
    .reshape(trunk + old_side + opp, 6),
    'W2': np.ones((4, 4), np.float32),
}
o = G.expand_side_arrays(d, n_out, old_side)
chk('W_side 行数 +9', o['W_side'].shape[0] == old_side + 9)
chk('W_side 尾部 9 行零',
    float(np.abs(o['W_side'][old_side:old_side + 9]).max()) == 0)
chk('W_side 前段保持', np.array_equal(o['W_side'][:old_side], d['W_side']))
chk('W1v 行数 +9', o['W1v'].shape[0] == trunk + old_side + 9 + opp)
cut = trunk + old_side
chk('W1v 尾部零段', float(np.abs(o['W1v'][cut:cut + 9]).max()) == 0)
chk('W1v 前段保持', np.array_equal(o['W1v'][:cut], d['W1v'][:cut]))
chk('其他键不变', np.array_equal(o['W2'], d['W2']))
S = np.ones((5, 5 * 88 + 358), np.float32)   # 旧宽=5N+358(实测生产)
S2 = G.pad_bc_S(S, 5 * 88 + 391)
chk('BC 尾补到 5N+391 且零列', S2.shape[1] == 5 * 88 + 391
    and float(np.abs(S2[:, S.shape[1]:]).max()) == 0)
chk('BC 前段保持', np.array_equal(S2[:, :S.shape[1]], S))
_src = open(os.path.join(WT, 'tools/migrate_gen2.py'), encoding='utf8').read()
chk('工具含 backup/atomic', 'backup' in _src and '.tmp' in _src)
chk('工具覆盖 plain 模型(2026-10-23 缺口)',
    "model_ppo_%s.npz" in _src
    and 'model_ppo_%s_fleet.npz' in _src)
tt = open(os.path.join(WT, 'train_tm.py'), encoding='utf8').read()
chk('train_tm FEAT_ACTABLE 接线',
    'TH123_FEAT_ACTABLE' in tt and '_actable_feats' in tt)
fb = open(os.path.join(WT, 'feat_builder.py'), encoding='utf8').read()
chk('feat_builder Gen-2 尾段', 'GEN2_TAIL' in fb
    and '_actable_feats' in fb and 'FEAT_WEATHER' in fb)
print('==== gen2 A v1: %d PASS / %d FAIL ====' % (13 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
