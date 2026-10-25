# -*- coding: utf-8 -*-
"""审计用 episodes 抽样（只读）: 近 N 局逐决策导出 state/act/mask/rew 供空间分析。

用法: python tools/episode_sample_for_audit.py --n 50 --out D:\\temp\\scratch
输出: episodes_sample_<ts>.npz + summary json（不含对手输入；episode 本身只含己方数据）
"""
import argparse
import glob
import io
import json
import os
import time

import numpy as np

EP = r'D:\temp\th123_models\fleet\episodes'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=50)
    ap.add_argument('--out', default=r'D:\temp\scratch')
    a = ap.parse_args()
    fs = sorted(glob.glob(os.path.join(EP, 'ep_*.npz')),
                key=os.path.getmtime)[-a.n:]
    out = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
           'dir': EP, 'files': [os.path.basename(f) for f in fs],
           'n': len(fs), 'per_file': []}
    rows = []
    for f in fs:
        try:
            with np.load(f, allow_pickle=True) as z:
                d = {k: (z[k] if k in z.files else None) for k in
                     ('acts', 'masks', 'rews', 'sides', 'meta', 'schema')}
            meta = str(d['meta']) if d['meta'] is not None else ''
            try:
                m = json.loads(meta)
            except Exception:
                m = {}
            n = int(len(d['acts'])) if d['acts'] is not None else 0
            rows.append({'file': os.path.basename(f), 'n': n,
                         'meta': {k: m.get(k) for k in
                                  ('char', 'ep', 'snap_ver', 'decisions')},
                         'acts_uniq': int(len(np.unique(d['acts'])))
                         if d['acts'] is not None else 0,
                         'rew_sum': float(np.asarray(d['rews']).sum())
                         if d['rews'] is not None else 0.0})
            out['per_file'].append(rows[-1])
        except Exception as e:
            out['per_file'].append({'file': os.path.basename(f),
                                    'err': repr(e)[:120]})
    ts = time.strftime('%Y%m%d_%H%M%S')
    pj = os.path.join(a.out, 'episodes_sample_%s.json' % ts)
    io.open(pj, 'w', encoding='utf-8').write(
        json.dumps(out, ensure_ascii=False, indent=1))
    print('[written]', pj, 'files', len(fs))
    print('说明: 逐决策 state 特征在 sides/feats; mask 在 masks; 奖励在 rews。'
          '本工具只读 episode（己方数据, 无对手输入）。')


if __name__ == '__main__':
    main()
