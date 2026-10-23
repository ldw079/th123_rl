# -*- coding: utf-8 -*-
"""task-50(C15): Gen-2 A 迁移工具纯函数 + CORE_DIMS 闸门."""
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
n_out, trunk, opp = 3, 7, 4
d = {
    'W_side': np.arange((2 * n_out + 382) * n_out, dtype=np.float32)
    .reshape(2 * n_out + 382, n_out),
    'Ws1.weight': np.arange((2 * n_out + 382) * 5, dtype=np.float32)
    .reshape(2 * n_out + 382, 5),
    'W1v': np.arange((trunk + 2 * n_out + 382 + opp) * 6,
                     dtype=np.float32).reshape(
        trunk + 2 * n_out + 382 + opp, 6),
    'W2': np.ones((4, 4), np.float32),
}
o = G.expand_side_arrays(d, n_out, trunk, opp)
chk('W_side 行数 +9', o['W_side'].shape[0] == 2 * n_out + 391)
chk('W_side 尾部 9 行零',
    float(np.abs(o['W_side'][2 * n_out + 382:2 * n_out + 391]).max()) == 0)
chk('W_side 前段保持', np.array_equal(o['W_side'][:2 * n_out], d['W_side'][:2 * n_out]))
chk('W1v 行数 +9', o['W1v'].shape[0] == trunk + 2 * n_out + 391 + opp)
chk('W1v 尾部零段',
    float(np.abs(o['W1v'][trunk + 2 * n_out + 382:
                          trunk + 2 * n_out + 391]).max()) == 0)
chk('其他键不变', np.array_equal(o['W2'], d['W2']))
S = np.ones((5, 5 * 88 + 382), np.float32)
S2 = G.pad_bc_S(S)
chk('BC 尾部 +9 零列', S2.shape[1] == 5 * 88 + 391
    and float(np.abs(S2[:, -9:]).max()) == 0)
chk('BC 前段保持', np.array_equal(S2[:, :5 * 88 + 382], S))
src = open(os.path.join(WT, 'tools/migrate_gen2.py'), encoding='utf8').read()
chk('工具含 backup/atomic', 'backup' in src and '.tmp' in src)
tt = open(os.path.join(WT, 'train_tm.py'), encoding='utf8').read()
chk('train_tm FEAT_ACTABLE 接线',
    'TH123_FEAT_ACTABLE' in tt and '_actable_feats' in tt)
fb = open(os.path.join(WT, 'feat_builder.py'), encoding='utf8').read()
chk('feat_builder Gen-2 尾段', 'GEN2_TAIL' in fb
    and '_actable_feats' in fb and 'FEAT_WEATHER' in fb)
print('==== gen2 A v1: %d PASS / %d FAIL ====' % (12 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
