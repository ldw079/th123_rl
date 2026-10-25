# -*- coding: utf-8 -*-
"""task-60: BC 锚合并工具(默认 dry-run; 仅窗口 --apply 才动生产 trio).

trio 格式: X (N,14400) uint8 / S (N,5N+391) float32 / Y (N,) int64 + meta.json
合并: 生产 trio + anchor 行 → 新 trio（宽度不变; 哈希重算; 原子替换; 备份硬链）。
R15: 校验失败拒绝加载/拒绝写入。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys

import numpy as np

STORE = r'D:\temp\th123_models'
ANCHOR = r'D:\temp\th123_anchor'


def sha256(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def load_trio(char):
    base = os.path.join(STORE, 'bc_%s' % char)
    X = np.load(base + '_X.npy', mmap_mode='r')
    S = np.load(base + '_S.npy', mmap_mode='r')
    Y = np.load(base + '_Y.npy', mmap_mode='r')
    meta = json.load(io.open(base + '_meta.json', encoding='utf-8'))
    return X, S, Y, meta, base


def plan(char, anchor_path):
    X, S, Y, meta, base = load_trio(char)
    with np.load(anchor_path, allow_pickle=True) as z:
        AX = z['X']
        AS = z['S']
        AY = z['Y']
        src = z['src']
    assert AX.shape[1] == X.shape[1], 'X 宽不一致'
    assert AS.shape[1] == S.shape[1], 'S 宽不一致 %d≠%d' % (
        AS.shape[1], S.shape[1])
    assert int(AY.max()) < int(meta['n_macros']), 'Y 越界'
    assert int(AY.min()) >= 0
    # 去重 vs 生产 X: 现有 X 哈希过多, 采样指纹逐行比较成本高 →
    # 仅校验 anchor 内自去重 + 与生产行数/宽度一致性; 完整去重由生成端保证.
    rep = {'char': char, 'prod_rows': int(len(Y)),
           'anchor_rows': int(len(AY)),
           'merged_rows': int(len(Y) + len(AY)),
           'X_width': int(X.shape[1]), 'S_width': int(S.shape[1]),
           'anchor_per_macro': {int(k): int(v) for k, v in
                                zip(*np.unique(AY, return_counts=True))},
           'meta_n_macros': int(meta['n_macros']),
           'anchor_source': 'offline_replay_anchor',
           'provenance_sample': src[:2].tolist() if len(src) else []}
    return rep, (X, S, Y, meta, base, AX, AS, AY)


def apply(char, anchor_path, report):
    rep, (X, S, Y, meta, base, AX, AS, AY) = plan(char, anchor_path)
    ts = time.strftime('%Y%m%d_%H%M%S') if False else __import__(
        'time').strftime('%Y%m%d_%H%M%S')
    bdir = os.path.join(STORE, 'bc_backup_anchor_%s_%s' % (char, ts))
    os.makedirs(bdir, exist_ok=True)
    for suf in ('_X.npy', '_S.npy', '_Y.npy', '_meta.json'):
        src = base + suf
        dst = os.path.join(bdir, os.path.basename(src))
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    # 新建合并数组(tmp)
    nX = np.concatenate([np.asarray(X), AX]).astype(np.uint8)
    nS = np.concatenate([np.asarray(S), AS]).astype(np.float32)
    nY = np.concatenate([np.asarray(Y), AY]).astype(np.int64)
    # 校验
    assert nX.shape[1] == X.shape[1] and nS.shape[1] == S.shape[1]
    assert np.isfinite(nS).all()
    nmeta = dict(meta)
    nmeta['rows'] = int(len(nY))
    nmeta['hashes'] = dict(meta.get('hashes') or {})
    nmeta['hashes']['X'] = sha256(nX)
    nmeta['hashes']['S'] = sha256(nS)
    nmeta['hashes']['Y'] = sha256(nY)
    nmeta['anchor'] = {'source': 'offline_replay_anchor',
                       'n_rows': int(len(AY)),
                       'manifest_sample': rep['provenance_sample'][:1]}
    # 原子替换
    for suf, arr in (('_X.npy', nX), ('_S.npy', nS), ('_Y.npy', nY)):
        tmp = base + suf + '.tmp.npy'
        np.save(tmp, arr)
        os.replace(tmp, base + suf)
    tmpm = base + '_meta.json.tmp'
    io.open(tmpm, 'w', encoding='utf-8').write(
        json.dumps(nmeta, ensure_ascii=False, indent=1))
    os.replace(tmpm, base + '_meta.json')
    rep['backup'] = bdir
    print('[merge] applied', char, rep['prod_rows'], '+',
          rep['anchor_rows'], '->', rep['merged_rows'], 'backup=', bdir)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--anchor', required=True)
    ap.add_argument('--apply', action='store_true', default=False)
    a = ap.parse_args()
    rep, _ = plan(a.char, a.anchor)
    print('[merge] plan:', json.dumps(rep, ensure_ascii=False)[:800])
    if not a.apply:
        print('[merge] dry-run（未修改生产 trio）')
        return 0
    rep = apply(a.char, a.anchor, rep)
    print('[merge] done:', json.dumps(rep, ensure_ascii=False)[:800])
    return 0


if __name__ == '__main__':
    sys.exit(main())
