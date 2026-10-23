# -*- coding: utf-8 -*-
"""task-35 C15: deck_cond 条件化采样(env/先验文件/权重生效/默认无偏置)."""
import importlib
import json
import os
import random
import sys

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


print('== deck_cond v1 ==')
PRI = os.path.join(WT, '_tmp_deck_cond_prior.json')
with open(PRI, 'w', encoding='utf8') as f:
    json.dump({'0': {'1': {'system': 0.0, 'skill': 0.0,
                           'sc': 10.0, 'mixed': 0.0}}}, f)
os.environ['TH123_DECK_COND'] = '1'
os.environ['TH123_DECK_COND_PRIOR'] = PRI
import deck_sampler as D  # noqa: E402
importlib.reload(D)
chk('env ON 读取先验', D.cond_arch_weights(0, 1) == {
    'system': 0.0, 'skill': 0.0, 'sc': 10.0, 'mixed': 0.0})
chk('缺项→None', D.cond_arch_weights(9, 9) is None)
rng = random.Random(7)
archs = [D.sample_deck_weighted(0, rng, cond=(0, 1))[1]
         for _ in range(20)]
chk('先验强偏置生效(sc 20/20)', archs.count('sc') == 20)
os.environ['TH123_DECK_COND'] = '0'
importlib.reload(D)
chk('env=0 无偏置', D.cond_arch_weights(0, 1) is None)
rng = random.Random(7)
a0 = {D.sample_deck_weighted(0, rng, cond=(0, 1))[1]
      for _ in range(40)}
chk('env=0 采样多流派(非单流派)', len(a0) >= 2)
os.environ['TH123_DECK_COND'] = '1'
os.environ['TH123_DECK_COND_PRIOR'] = PRI + '.missing'
importlib.reload(D)
chk('先验文件缺失→None(无行为变化)', D.cond_arch_weights(0, 1) is None)
try:
    os.remove(PRI)
except OSError:
    pass
src = open(os.path.join(WT, 'train_tm.py'), encoding='utf8').read()
chk('train_tm 传入 cond=(我,敌)', 'cond=(CHAR_LIBS[self.char][\'id\']' in src)
os.environ['TH123_DECK_COND'] = '0'
print('==== deck_cond v1: %d PASS / %d FAIL ====' % (8 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
