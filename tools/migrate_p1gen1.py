# -*- coding: utf-8 -*-
"""Gen-1 迁移工具 v2: 只加 mem_*/W_mem(不扩 Ws1) → env=0 可直读迁移后档."""
import argparse
import os
import shutil
import sys

import numpy as np

CHARS = {'reimu': 88, 'marisa': 95, 'suika': 91}
MEM_IN, MEM_HID, MEM_OUT = 27, 32, 64


def migrate_one(pi, vv, n_out, dry):
    d = np.load(pi)
    if 'mem_dim' in d.files:
        print('[skip] 已迁移:', os.path.basename(pi))
        return False
    rng = np.random.default_rng(20261020 + n_out)
    out = {k: d[k] for k in d.files
           if k not in ('Wf1', 'bf1', 'Wf2', 'bf2', 'mem_dim',
                        'mem_fc1', 'mem_b1', 'mem_fc2', 'mem_b2', 'W_mem')}
    out['mem_dim'] = np.array([8], dtype=np.int64)
    out['mem_fc1'] = (rng.standard_normal((MEM_IN, MEM_HID))
                      / np.sqrt(MEM_IN)).astype(np.float32)
    out['mem_b1'] = np.zeros(MEM_HID, dtype=np.float32)
    # task-40: mem_fc2 必须非零小随机, 否则 W_mem 输入恒零→恒零梯度(死分支)
    out['mem_fc2'] = (rng.standard_normal((MEM_HID, MEM_OUT)) * 0.05
                      ).astype(np.float32)
    out['mem_b2'] = np.zeros(MEM_OUT, dtype=np.float32)
    out['W_mem'] = np.zeros((MEM_OUT, n_out), dtype=np.float32)
    if dry:
        print('[dry]', os.path.basename(pi))
        return True
    for p in (pi, vv):
        bk = p.replace('.npz', '_pre_p1gen1.npz')
        if not os.path.exists(bk):
            shutil.copy2(p, bk)
        else:
            print('[warn] 备份已存在不覆盖: %s (回滚请用窗内备份目录)'
                  % os.path.basename(bk))
    np.savez(pi, **out)
    print('[ok] %s +mem/W_mem (Wf stripped), 备份 *_pre_p1gen1.npz'
          % os.path.basename(pi))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store',
                    default=os.environ.get('TH123_STORE',
                                           r'D:\temp\th123_models'))
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    changed = 0
    for ch, n_out in CHARS.items():
        pi = os.path.join(a.store, 'model_ppo_%s_fleet.npz' % ch)
        vv = os.path.join(a.store, 'model_ppo_%s_fleet_v.npz' % ch)
        if os.path.exists(pi) and migrate_one(pi, vv, n_out, a.dry):
            changed += 1
    print('[done] migrated', changed)


if __name__ == '__main__':
    main()
