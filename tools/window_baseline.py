# -*- coding: utf-8 -*-
"""窗基线采集 v2: frame_logs 实际路径/受身机会/完整 JSON+sha256.

用法: python tools/window_baseline.py --out <json> [--minutes 60]
frame_logs: STORE/frame_logs/<char>/fl_*.pkl (dict: fields/frames/decisions)
受身机会: frame 中左方 action 进入 knockdown(50-78) 的次数（口径写 prereg）。
"""
import argparse
import glob
import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
STORE = r'D:\temp\th123_models'
FLEET = os.path.join(STORE, 'fleet')
FRAME_ROOT = os.path.join(STORE, 'frame_logs')
EPISODES = os.path.join(FLEET, 'episodes')
KNOCK = set(range(50, 79))


def sha_file(p):
    try:
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def count_ukemi_opportunities(files):
    """受身机会=左方 action 进入 knockdown(50-78) 的次数（帧档口径）."""
    n = 0
    for p in files:
        try:
            d = pickle.load(open(p, 'rb'))
        except Exception:
            continue
        prev = None
        for fr in d.get('frames') or []:
            try:
                left = fr[0]
                act = int(left[4])
            except Exception:
                continue
            in_knock = act in KNOCK
            if in_knock and not prev:
                n += 1
            prev = in_knock
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=r'D:\temp\window_baseline.json')
    ap.add_argument('--minutes', type=int, default=60)
    a = ap.parse_args()
    now = time.time()
    cut = now - a.minutes * 60
    rep = {'ts': now, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
           'window_minutes': a.minutes,
           'definitions': {
               'frame_file': 'STORE/frame_logs/<char>/fl_*.pkl',
               'decisions': 'frame_logs decisions 条数(优先)/episode acts',
               'ukemi_opportunity':
               '左方 action 进入 knockdown(50-78) 的次数（帧档口径）'},
           'chars': {}}
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    for ch in ('reimu', 'marisa', 'suika'):
        d = os.path.join(FRAME_ROOT, ch)
        fl = [p for p in glob.glob(os.path.join(d, 'fl_*.pkl'))
              if os.path.getmtime(p) > cut] if os.path.isdir(d) else []
        dec = 0
        for p in fl:
            try:
                with open(p, 'rb') as f:
                    dd = pickle.load(f)
                dec += len(dd.get('decisions') or [])
            except Exception:
                pass
        eps = [p for p in glob.glob(os.path.join(EPISODES, 'ep_*.npz'))
               if os.path.getmtime(p) > cut]
        if dec == 0:
            for p in eps:
                try:
                    with np.load(p, allow_pickle=True) as z:
                        if 'acts' in z.files:
                            dec += int(len(z['acts']))
                except Exception:
                    pass
        opp = count_ukemi_opportunities(fl)
        mc_path = os.path.join(STORE, 'macro_counts_%s_fleet.npy' % ch)
        try:
            mc = np.load(mc_path).astype(np.int64)
            mc_hash = sha_bytes(mc.tobytes())
        except Exception:
            mc_hash = None
        rep['chars'][ch] = {
            'frame_files_lastN': len(fl),
            'frame_files': [os.path.basename(p) for p in fl[-5:]],
            'decisions_lastN': dec,
            'episodes_lastN': len(eps),
            'ukemi_opportunities_lastN': opp,
            'macro_counts_sha256': mc_hash,
        }
    rep['hashes'] = {
        'bat': sha_file(r'D:\temp\train_batch_launch.bat'),
        'fleet_supervisor': sha_file(os.path.join(ROOT, 'fleet_supervisor.py')),
        'fleet_health': sha_file(os.path.join(ROOT, 'tools',
                                              'fleet_health.py')),
        'model_reimu': sha_file(os.path.join(STORE, 'model_ppo_reimu.npz')),
    }
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    raw = json.dumps(rep, ensure_ascii=False, indent=1).encode('utf-8')
    with open(a.out, 'wb') as f:
        f.write(raw)
    rep['baseline_path'] = os.path.abspath(a.out)
    rep['baseline_sha256'] = sha_bytes(raw)
    print(json.dumps({k: rep[k] for k in ('baseline_path',
                                          'baseline_sha256',
                                          'hashes')}, ensure_ascii=False))
    print(json.dumps(rep['chars'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
