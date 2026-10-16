# -*- coding: utf-8 -*-
"""CH-3/JZ-4宏库扩展波迁移: 模型/种子档宏数扩到现行代码值(load零初始化+save)。

- ppo.load宏扩展路径: 新宏零初始化, 旧宏策略逐位保持(check_model_generation
  依据"模型n_out==代码宏数", 不迁移=learner拒启)。
- 迁移前备份STORE/macro_wave_backup(回滚=拷回)。
- 只动n_out≠现行宏数的档; 相同跳过; 宽度断言照旧(5N+CORE_DIMS同步长大)。
"""
import glob
import os
import re
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

from ppo import PPOTrainer  # noqa
from feat_builder import FeatureBuilder  # noqa
from train_tm import CHAR_LIBS  # noqa

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
BAK = os.path.join(STORE, 'macro_wave_backup')


def cur_n(char):
    return len(CHAR_LIBS[char]['macros'])


def migrate_pattern(pattern, char_of, label):
    n = odd = 0
    for p in sorted(glob.glob(pattern)):
        b = os.path.basename(p)
        if '_v' in b and '_v.npz' in b:
            continue
        if b.endswith('_v.npz'):
            continue
        d = np.load(p)
        if 'W2' not in d.files:
            d.close()
            continue
        n_out = int(d['W2'].shape[1])
        w_side = int(d['W_side'].shape[0]) if 'W_side' in d.files else -1
        d.close()
        ch = char_of(p)
        if ch is None:
            continue
        target = cur_n(ch)
        if n_out == target:
            # 宽度若还是旧宏数推导值 → 需重迁(宏数变了侧宽跟着变)
            if w_side == 5 * target + FeatureBuilder.CORE_DIMS:
                continue
        v = p.replace('.npz', '_v.npz')
        if not os.path.exists(v):
            print('  %s: 无v档 — 跳过!' % b)
            odd += 1
            continue
        os.makedirs(BAK, exist_ok=True)
        for src in (p, v):
            dst = os.path.join(BAK, label + '_' + os.path.basename(src))
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
        t = PPOTrainer(n_side=5 * target + FeatureBuilder.CORE_DIMS,
                       n_out=target)
        t.load(p, v)
        t.save(p, v)
        d2 = np.load(p)
        assert int(d2['W2'].shape[1]) == target, b
        assert int(d2['W_side'].shape[0]) == 5 * target + \
            FeatureBuilder.CORE_DIMS, b
        d2.close()
        print('  %s: n_out %d→%d, side %d→%d ✓'
              % (b, n_out, target, w_side,
                 5 * target + FeatureBuilder.CORE_DIMS))
        n += 1
    return n, odd


def main():
    print('现行宏数:', {ch: cur_n(ch) for ch in ('reimu', 'marisa', 'suika')})
    n1, o1 = migrate_pattern(
        os.path.join(STORE, 'model_ppo_*.npz'),
        lambda p: re.match(r'model_ppo_([a-z]+)', os.path.basename(p))
        .group(1), 'model')
    n2, o2 = migrate_pattern(
        os.path.join(STORE, 'fleet', 'pool', '*', 'seed_*.npz'),
        lambda p: os.path.basename(os.path.dirname(p)), 'seed')
    print('\n模型迁移%d 种子迁移%d 异常%d+%d; 备份: %s'
          % (n1, n2, o1, o2, BAK))


if __name__ == '__main__':
    main()
