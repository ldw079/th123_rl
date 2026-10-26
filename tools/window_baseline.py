# -*- coding: utf-8 -*-
"""UKEMI/窗基线采集: dir_f/dir_b 基线、样本门计数、hash、窗起时刻.

用法: python tools/window_baseline.py --out <json> [--minutes 60]
输出（窗起日志）：per char decisions(episode acts), frame档数, UKEMI 机会(基线),
macro_counts 快照 hash, bat/config/model hash, 窗起时刻。
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
STORE = r'D:\temp\th123_models'
FLEET = os.path.join(STORE, 'fleet')
FRAME_LOGS = os.path.join(FLEET, 'frame_logs')
EPISODES = os.path.join(FLEET, 'episodes')


def sha_file(p):
    try:
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=r'D:\temp\window_baseline.json')
    ap.add_argument('--minutes', type=int, default=60)
    a = ap.parse_args()
    now = time.time()
    cut = now - a.minutes * 60
    rep = {'ts': now, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
           'window_minutes': a.minutes, 'chars': {}}
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    from train_tm import CHAR_LIBS
    for ch in ('reimu', 'marisa', 'suika'):
        names = [m[0] for m in CHAR_LIBS[ch]['macros']]
        idx = {n: i for i, n in enumerate(names)}
        mc_path = os.path.join(STORE, 'macro_counts_%s_fleet.npy' % ch)
        try:
            mc = np.load(mc_path).astype(np.int64)
            mc_hash = hashlib.sha256(mc.tobytes()).hexdigest()[:16]
            base_f = int(mc[idx['前进']]) if '前进' in idx else 0
            base_b = int(mc[idx['后退']]) if '后退' in idx else 0
        except Exception:
            mc, mc_hash, base_f, base_b = None, None, 0, 0
        # decisions/frame档: episode 文件(近 N 分钟)
        eps = [p for p in glob.glob(os.path.join(EPISODES, 'ep_*.npz'))
               if os.path.getmtime(p) > cut]
        dec = 0
        for p in eps:
            try:
                with np.load(p, allow_pickle=True) as z:
                    if 'acts' in z.files:
                        dec += int(len(z['acts']))
            except Exception:
                pass
        fl = [p for p in glob.glob(os.path.join(FRAME_LOGS, '*.log'))
              if os.path.getmtime(p) > cut] if os.path.isdir(FRAME_LOGS) else []
        rep['chars'][ch] = {
            'decisions_lastN': dec,
            'episodes_lastN': len(eps),
            'frame_files_lastN': len(fl),
            'ukemi_opportunities_baseline': 0,
            'ukemi_note': '窗起基线=0 起点；受身机会由窗内 frame 解析计数(口径见 prereg)',
            'dir_f_baseline_count': base_f,
            'dir_b_baseline_count': base_b,
            'macro_counts_hash': mc_hash,
        }
    rep['hashes'] = {
        'bat': sha_file(r'D:\temp\train_batch_launch.bat'),
        'fleet_supervisor': sha_file(os.path.join(ROOT, 'fleet_supervisor.py')),
        'fleet_health': sha_file(os.path.join(ROOT, 'tools',
                                              'fleet_health.py')),
        'model_reimu': sha_file(os.path.join(STORE, 'model_ppo_reimu.npz')),
    }
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False)[:600])
    return 0


if __name__ == '__main__':
    sys.exit(main())
