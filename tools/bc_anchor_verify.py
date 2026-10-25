# -*- coding: utf-8 -*-
"""task-60 v2 独立校验: 锚 npz QC + P0-1 泄漏检查 + 独立盲复验抽样 + 配额/冲突.

用法: python tools/bc_anchor_verify.py --char reimu --npz <path> [--blind 50]
输出: D:\temp\scratch\bc_anchor_v2_qc.md / .json
"""
import argparse
import glob
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import bc_io  # noqa: E402
import bc_anchor_collect as A  # noqa: E402

STORE = r'D:\temp\th123_models'
OUT_MD = r'D:\temp\scratch\bc_anchor_v2_qc.md'
OUT_JS = r'D:\temp\scratch\bc_anchor_v2_qc.json'


def load(npz):
    with np.load(npz, allow_pickle=True) as z:
        return (z['X'], z['S'], z['Y'],
                z['src'] if 'src' in z.files else np.array([]))


def verify(char, npz, blind=50, port=21097):
    X, S, Y, src = load(npz)
    n = int(len(A.CHAR_LIBS[char]['macros']))
    prodS = np.load('%s/bc_%s_S.npy' % (STORE, char), mmap_mode='r')
    prodY = np.load('%s/bc_%s_Y.npy' % (STORE, char), mmap_mode='r')
    prodX = np.load('%s/bc_%s_X.npy' % (STORE, char), mmap_mode='r')
    rep = {'char': char, 'npz': os.path.basename(npz),
           'rows': int(len(Y)), 'n_macros': n,
           'X_width': int(X.shape[1]), 'S_width': int(S.shape[1]),
           'widths_match': X.shape[1] == prodX.shape[1]
           and S.shape[1] == prodS.shape[1],
           'Y_range': [int(Y.min()), int(Y.max())],
           'Y_ok': bool(0 <= Y.min() and Y.max() < n)}
    # P0-1 泄漏逐行检查
    leak = int(np.sum(S[np.arange(len(Y)), Y] > 1e-6)
               + np.sum(S[np.arange(len(Y)), n + Y] > 1e-6))
    rep['target_leak_rows'] = leak
    # src 解析 + combo_ok/heldout
    rows = []
    for s in src:
        try:
            rows.append(json.loads(str(s)))
        except Exception:
            rows.append({})
    ok_n = 0
    held_n = held_ok = 0
    for r in rows:
        dmg = float(r.get('dmg', 0))
        acts = r.get('acts') or []
        if A.combo_ok(dmg, acts):
            ok_n += 1
        h = r.get('heldout') or {}
        if h:
            held_n += 1
            held_ok += 1 if h.get('ok') else 0
    rep['combo_ok_rows'] = ok_n
    rep['combo_ok_rows'] = ok_n
    rep['combo_ok_rate'] = round(ok_n / max(1, rep['rows']), 3)
    rep['heldout_n'] = held_n
    rep['heldout_ok'] = held_ok
    rep['heldout_rate'] = round(held_ok / max(1, held_n), 3)
    # 配额/冲突
    per = {int(k): int(v) for k, v in zip(*np.unique(Y, return_counts=True))}
    rep['per_macro'] = per
    rep['quota_min'] = min(per.values()) if per else 0
    # 独立盲复验抽样: 用 src.seq RLE 解压后在新对局盲放(不经过 executor)
    blind_res = []
    if blind > 0 and len(rows):
        try:
            env = A.EvalEnv(port, char_left=char, char_right=char,
                            vs_com=False, tps=360)
            try:
                for _ in range(240):
                    if A.step(env, dict(A.NEUTRAL), dict(A.NEUTRAL)) is None:
                        break
                idxs = np.linspace(0, len(rows) - 1,
                                   num=min(blind, len(rows))).astype(int)
                for i in idxs:
                    r = rows[int(i)]
                    pos = r.get('gen_pos') or [500.0, 60.0, 0.0]
                    seq = r.get('seq') or []
                    inputs = []
                    for key, cnt in seq:
                        d = dict(A.NEUTRAL)
                        for k, v in key:
                            d[k] = v
                        inputs += [d] * int(cnt)
                    sc = r.get('scenario', 'mid')
                    if sc == 'wakeup':
                        r0 = A.sync(env, pos[0], pos[0] + pos[1])
                        if r0 is not None:
                            for keys in ({'C': True, 'V': 1},
                                         {'C': True}):
                                for _ in range(8):
                                    A.step(env, dict(A.NEUTRAL, **keys), {})
                    else:
                        r0 = A.sync(env, pos[0], pos[0] + pos[1],
                                    float(pos[2]))
                    if r0 is None:
                        blind_res.append({'i': int(i), 'ok': False,
                                          'err': 'sync'})
                        continue
                    # 与生成侧对齐: sync 后有 6 帧 idle lead-in 才到决策点
                    for _ in range(6):
                        A.step(env, dict(A.NEUTRAL), {})
                    dmg, acts = A.blind_run(env, inputs)
                    ok = A.combo_ok(dmg, acts)
                    blind_res.append({'i': int(i), 'ok': bool(ok),
                                      'dmg': round(float(dmg), 1),
                                      'macro': r.get('macro')})
            finally:
                try:
                    env.close()
                except Exception:
                    pass
        except Exception as e:
            blind_res.append({'err': repr(e)[:120]})
    rep['blind'] = {'n': len([b for b in blind_res if 'err' not in b]),
                    'ok': len([b for b in blind_res if b.get('ok')]),
                    'samples': blind_res[:80]}
    if rep['blind']['n']:
        rep['blind']['rate'] = round(rep['blind']['ok']
                                     / rep['blind']['n'], 3)
    # 与生产 X 去重(抽样估计; 全量成本高, 记样本)
    rep['note'] = '独立盲复验=新对局按 src.seq 盲放(不经 executor); '\
                  'P0-1 泄漏逐行检查 S[Y]/S[N+Y]'
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--npz', default=None)
    ap.add_argument('--blind', type=int, default=50)
    a = ap.parse_args()
    npz = a.npz
    if not npz:
        fs = sorted(glob.glob(r'D:\temp\th123_anchor\bc_anchor_%s_*.npz'
                              % a.char))
        npz = fs[-1]
    rep = verify(a.char, npz, a.blind)
    allrep = {}
    if os.path.exists(OUT_JS):
        try:
            allrep = json.load(io.open(OUT_JS, encoding='utf-8'))
        except Exception:
            allrep = {}
    allrep[a.char] = rep
    io.open(OUT_JS, 'w', encoding='utf-8').write(
        json.dumps(allrep, ensure_ascii=False, indent=1))
    L = ['# BC 锚 v2 QC（独立校验）', '',
         '## %s' % a.char, '',
         '- npz `%s`；rows=%d；宽度匹配=%s；Y范围=%s(ok=%s)'
         % (rep['npz'], rep['rows'], rep['widths_match'], rep['Y_range'],
            rep['Y_ok']),
         '- **P0-1 目标泄漏行数: %d（必须=0）**' % rep['target_leak_rows'],
         '- combo_ok(dmg>=300 & >=2act): %d/%d=%.3f'
         % (rep['combo_ok_rows'], rep['rows'], rep['combo_ok_rate']),
         '- held-out 独立盲复验(采集内): %d/%d=%.3f'
         % (rep['heldout_ok'], rep['heldout_n'], rep['heldout_rate']),
         '- 独立盲放抽样: n=%d ok=%d rate=%s'
         % (rep['blind'].get('n', 0), rep['blind'].get('ok', 0),
            rep['blind'].get('rate')),
         '- 每宏配额: min=%d; %s' % (rep['quota_min'], rep['per_macro'])]
    io.open(OUT_MD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
