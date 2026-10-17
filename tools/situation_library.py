# -*- coding: utf-8 -*-
"""LE-1a(学习效率方案v2§LE-1a): 情境库构建 — 纯离线, 不触训练.

设计(v1, 2026-10-17):
  情境 = 新BC库行(X/S/Y mmap) + S派生标签 + BH-1旁车热度:
    matchup: 对位one-hot直读(段11槽227+oid / 扩展区308+i) — 20角色
    corner:  core[149]/[150]贴角位>0.9
    near:    core[4]=clip(adx/600)∈[0.2,0.5](adx 120-300px, 近距)
    attack:  Y∈角色attack宏集(CHAR_LIBS)
  热度(heat): bh旁车聚合的该对位连段打断率(高=弱点情境, LE-1b
  注入优先级) — 读behavior_health.aggregate, 动态刷新.
  TTL: 自打源弱点情境(frame日志)二期 — 帧日志刚启用累积; oracle源
  行永久(专家知识不过期, 文档化).

用法:
  python tools/situation_library.py --char reimu          # 构建/刷新
  python tools/situation_library.py --char reimu --stats  # 只看统计
查询API: situation_library.query(char, tags, k) → 行索引(LE-1b注入用)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
OUT_DIR = os.path.join(ROOT, 'data', 'situations')

# 标签位(bit layout)
TAG_MATCHUP = 0      # 0-19存matchup_id列
TAG_CORNER = 20
TAG_NEAR = 21
TAG_ATTACK = 22
N_TAG_COLS = 23

from train_tm import CHAR_LIBS  # noqa: E402
from bc_io import load_bank      # noqa: E402


def derive_tags(S_arr, Y, char):
    """S(m,n_side)×Y(m,) → (m, 23)标签阵.
    注意绝对列=2n+core偏移(R153排错: 首版漏加2n, 读到one-hot块
    产出伪分布 — 布局账: [0:n]上宏[n:2n]上上宏[2n:2n+CORE]core)."""
    m = S_arr.shape[0]
    n = len(CHAR_LIBS[char]['macros'])
    O = 2 * n
    tags = np.zeros((m, N_TAG_COLS), dtype=np.float32)
    # matchup one-hot (m,)
    mid = np.full(m, -1, dtype=np.int8)
    for o in (0, 1, 2):
        mid = np.where(mid < 0, np.where(
            S_arr[:, O + 227 + o] > 0.9, o, mid), mid)
    for j in range(11, 20):
        mid = np.where(mid < 0, np.where(
            S_arr[:, O + 227 + j] > 0.9, j, mid), mid)
    for k in range(8):
        mid = np.where(mid < 0, np.where(
            S_arr[:, O + 308 + k] > 0.9, 20 + k, mid), mid)
    ok = mid >= 0
    tags[ok, TAG_MATCHUP] = mid[ok]
    # corner / near / attack  (near: adx 120-300px = core[4]∈[0.2,0.5]
    # — 实测分位10%=43px/50%=202px/90%=579px, 近距带合理)
    tags[:, TAG_CORNER] = ((S_arr[:, O + 149] > 0.9)
                           | (S_arr[:, O + 150] > 0.9))
    tags[:, TAG_NEAR] = ((S_arr[:, O + 4] >= 0.2) & (S_arr[:, O + 4] <= 0.5))
    atk = np.zeros(len(CHAR_LIBS[char]['macros']), dtype=bool)
    for i, (nm, _s) in enumerate(CHAR_LIBS[char]['macros']):
        atk[i] = nm in CHAR_LIBS[char]['attack']
    tags[:, TAG_ATTACK] = atk[Y]
    return tags, mid


def matchup_heat(char):
    """BH-1旁车→对位热度(打断率; 无数据→空)."""
    from behavior_health import aggregate
    agg = aggregate(os.path.join(STORE, 'fleet', 'episodes'), char, 200)
    heat = {}
    ID2NAME = {l['id']: n for n, l in CHAR_LIBS.items()}
    for oc, d in agg.get('combo_by_opp', {}).items():
        n = sum(d.values())   # 条目无'n'键(rates()才加) — 原d.get('n',0)恒0
        if n >= 5 and oc in ID2NAME.values():
            oid = next(i for i, nm in ID2NAME.items() if nm == oc)
            heat[int(oid)] = round(1.0 - d.get('hit_rate', 0.0), 3)
    return heat


def build(char, verbose=True):
    bank = load_bank(char, store=STORE)
    if bank is None:
        print('[%s] 无BC库' % char)
        return None
    X, S, Y = bank
    m = len(Y)
    # 分块派生(mmap S, 内存限流)
    tags_l, mid_l = [], []
    CH = 65536
    for i0 in range(0, m, CH):
        blk = np.asarray(S[i0:i0 + CH])
        t, mid = derive_tags(blk, np.asarray(Y[i0:i0 + CH]), char)
        tags_l.append(t)
        mid_l.append(mid)
    tags = np.concatenate(tags_l)
    mid = np.concatenate(mid_l)
    heat = matchup_heat(char)
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, '%s_index.npz' % char)
    tmp = p + '.tmp.npz'
    np.savez(tmp, tags=tags, matchup=mid,
             meta=np.array(json.dumps({
                 'char': char, 'rows': int(m),
                 'n_matchup': int((mid >= 0).sum()),
                 'heat': heat, 'built': __import__('time').strftime(
                     '%Y%m%d_%H%M%S')})))
    os.replace(tmp, p)
    if verbose:
        from collections import Counter
        c = Counter(int(x) for x in mid if x >= 0)
        top = ', '.join('%s:%d' % (
            next((n for n, l in CHAR_LIBS.items() if l['id'] == k), k), v)
            for k, v in c.most_common(6))
        print('[%s] %d行 | 对位标注%.1f%% (%s)' % (
            char, m, 100 * (mid >= 0).mean(), top))
        print('  贴角%.1f%% 近距%.1f%% 攻击标签%.1f%% | 热度%d对位' % (
            100 * tags[:, TAG_CORNER].mean(),
            100 * tags[:, TAG_NEAR].mean(),
            100 * tags[:, TAG_ATTACK].mean(), len(heat)))
    return p


def query(char, matchup=None, corner=None, near=None, attack=None,
          k=64, heat_weighted=False):
    """查询情境行索引(LE-1b注入入口)."""
    p = os.path.join(OUT_DIR, '%s_index.npz' % char)
    if not os.path.exists(p):
        return None
    d = np.load(p, allow_pickle=True)
    tags, mid = d['tags'], d['matchup']
    sel = np.ones(len(mid), dtype=bool)
    if matchup is not None:
        sel &= (mid == matchup)
    if corner is not None:
        sel &= (tags[:, TAG_CORNER] > 0) == corner
    if near is not None:
        sel &= (tags[:, TAG_NEAR] > 0) == near
    if attack is not None:
        sel &= (tags[:, TAG_ATTACK] > 0) == attack
    idx = np.where(sel)[0]
    if heat_weighted and matchup is not None:
        meta = json.loads(str(d['meta']))
        h = meta.get('heat', {}).get(str(int(matchup)))
        if h:
            # 热度加权下采样: 弱点对位全取, 强势对位按(1-h)保留
            keep = np.random.default_rng(7).random(len(idx)) < (1.0 - h)
            idx = idx[keep]
    return idx[:k] if k else idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu,marisa,suika')
    ap.add_argument('--stats', action='store_true')
    a = ap.parse_args()
    for ch in a.char.split(','):
        if a.stats:
            p = os.path.join(OUT_DIR, '%s_index.npz' % ch)
            if os.path.exists(p):
                d = np.load(p, allow_pickle=True)
                print(json.loads(str(d['meta'])))
            else:
                print('[%s] 未构建' % ch)
        else:
            build(ch)


if __name__ == '__main__':
    main()
