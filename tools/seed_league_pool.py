# -*- coding: utf-8 -*-
"""D3'(R65): league 20角色对手生态 — 静态种子入fleet池.

定位: 17个非主角色(BC/trialmode初始化模型, 无learner=永不更新)作为
league多样性锚点, 以seed_前缀快照进入 {fleet}/pool/{char}/。actor的
_resolve_pool动态解析+维度守卫+league加权照常生效; 种子永不滚动清理
(learner的POOL_KEEP清理只动**自己角色**目录, 不碰league角色)。

对手特征/卡组前置(均已验证): _CHAR_POOL_IDX 20角色全唯一映射(R61t/F5)、
CHAR_LIBS 20套宏库、deck_sampler技能/SC表20角色全覆盖。

用法:
  python tools/seed_league_pool.py                 # 种子缺失的league角色
  python tools/seed_league_pool.py --refresh       # 强制重种(新的时间戳)
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
FOCUS_DEFAULT = ('reimu', 'marisa', 'suika')


def seed_league_pool(store=STORE, focus=FOCUS_DEFAULT, refresh=False,
                     verbose=True):
    """把league角色(非focus)的生产模型种入fleet池。

    返回 (seeded, skipped, rejected):
      seeded   = 成功种入的角色列表
      skipped  = 已有种子且未refresh的角色列表(幂等跳过)
      rejected = 模型缺档/维度守卫不过的角色列表(带原因, 不中断其余)
    """
    from train_tm import CHAR_LIBS, _pool_snapshot_ok

    fleet_pool = os.path.join(store, 'fleet', 'pool')
    league = [c for c in CHAR_LIBS if c not in focus]
    seeded, skipped, rejected = [], [], []
    ts = time.strftime('%Y%m%d_%H%M%S')
    for ch in league:
        d = os.path.join(fleet_pool, ch)
        # 排除_v档(outer_loop同款坑: seed_*_v.npz也匹配seed_*.npz)
        have = [f for f in glob.glob(os.path.join(d, 'seed_*.npz'))
                if not f.endswith('_v.npz')]
        if have and not refresh:
            skipped.append(ch)
            continue
        src = os.path.join(store, 'model_ppo_%s.npz' % ch)
        if not os.path.exists(src):
            rejected.append('%s(缺模型档)' % ch)
            continue
        # 维度守卫(与actor侧_resolve_pool同判据 — 种时就拦, 不等actor跳过)
        n_macros = len(CHAR_LIBS[ch]['macros'])
        if not _pool_snapshot_ok(src, n_macros):
            rejected.append('%s(宏数不符)' % ch)
            continue
        os.makedirs(d, exist_ok=True)
        # 先v后pi=配对提交标记(outer_loop约定); v缺失只警告(对手只需策略网)
        vsrc = src.replace('.npz', '_v.npz')
        if os.path.exists(vsrc):
            shutil.copy2(vsrc, os.path.join(d, 'seed_%s_v.npz' % ts))
        elif verbose:
            print('[seed] %s 无_v档 — 只种策略网(对手侧够用)' % ch)
        shutil.copy2(src, os.path.join(d, 'seed_%s.npz' % ts))
        seeded.append(ch)
        if verbose:
            print('[seed] %s → fleet/pool (%d宏)' % (ch, n_macros))
    return seeded, skipped, rejected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default=STORE)
    ap.add_argument('--focus', default=','.join(FOCUS_DEFAULT),
                    help='主角色(有learner的, 逗号分隔)')
    ap.add_argument('--refresh', action='store_true',
                    help='已有种子也重种(新时间戳)')
    args = ap.parse_args()
    focus = tuple(c.strip() for c in args.focus.split(',') if c.strip())
    seeded, skipped, rejected = seed_league_pool(
        args.store, focus, args.refresh)
    print('种子%d个: %s' % (len(seeded), ','.join(seeded) or '-'))
    print('跳过% d个(已有种子): %s' % (len(skipped), ','.join(skipped) or '-'))
    if rejected:
        print('拒收%d个: %s' % (len(rejected), ' '.join(rejected)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
