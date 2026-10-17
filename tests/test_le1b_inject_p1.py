# -*- coding: utf-8 -*-
"""P1-3/14/15(从零#5)行为测试: LE-1b 热度注入四重失效的修复必须真实生效。

审计实证的四重失效(全部亲验过):
  ① `le1b_inject` **从不传 matchup** → query 内 `if heat_weighted and matchup
     is not None` 恒假 → 热度分支从不执行(实测返回全量 66,940 行);
  ② 极性反: `keep = rng < (1-h)`, 而设计是"弱点对位(h高)全取" → h=1.0 时保留 **0** 行;
  ③ id 空间错位: heat 键是 raw char id(9=萃香), mid 是池槽(2) → suika 自镜像
     永不命中, '2'(咲夜 raw)还会错配到萃香行;
  ④ 20% 上限从未生效: ratio=0.5/1.0 时注入 32/64 行(占批 50%/100%)。

本测试用**合成索引**(temp OUT_DIR) 钉死语义, 再用真实产物做前提核对 —
这样沙箱内也能跑, 且不依赖重建后的新库。
"""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), 'tools'))
sys.stdout.reconfigure(encoding='utf8')

import situation_library as SL          # noqa: E402
import le1b_inject as L                 # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    print('  %s  %s' % ('PASS' if cond else 'FAIL', name))
    if not cond:
        BAD += 1


# ── 1. raw id → 池槽 映射(单源) ──
r2p = SL.raw_to_pool()
ck(r2p.get(9) == 2, 'raw 9(萃香) → 池槽 2: %r' % (r2p.get(9),))
ck(r2p.get(0) == 0, 'raw 0(灵梦) → 池槽 0: %r' % (r2p.get(0),))

# ── 合成索引: mid 用池槽(0/1/2), heat 故意用 **raw id** 键(复现旧产物形态) ──
TMP = tempfile.mkdtemp(prefix='_le1b_p1_')
_orig_out = SL.OUT_DIR
SL.OUT_DIR = TMP
try:
    ROWS = 400
    mid = np.zeros(ROWS, dtype=np.int64)
    mid[:100] = 0          # 池槽0
    mid[100:200] = 1       # 池槽1
    mid[200:] = 2          # 池槽2(萃香=raw 9)
    _NTAG = max(SL.TAG_ATTACK, SL.TAG_NEAR, SL.TAG_CORNER) + 1
    tags = np.zeros((ROWS, _NTAG), dtype=np.int8)
    tags[:, SL.TAG_ATTACK] = 1
    tags[:, SL.TAG_NEAR] = 1
    meta = {'char': 'suika', 'rows': ROWS,
            'heat': {'0': 0.5, '1': 1.0, '9': 0.95}}   # raw 键 → 槽 2 需反查
    np.savez(os.path.join(TMP, 'suika_index.npz'), tags=tags, matchup=mid,
             meta=np.array(json.dumps(meta)))

    # ── 2. 旧产物(raw 键) → 池槽查询必须能命中(反查兼容) ──
    z = SL.query('suika', matchup=2, k=0, heat_weighted=False)
    ck(z is not None and len(z) == 200, '池槽2 无热度过滤=200行: %r'
       % (None if z is None else len(z)))
    h = SL.query('suika', matchup=2, k=0, heat_weighted=True)
    ck(h is not None and 0 < len(h) <= len(z),
       '池槽2 热度过滤(raw键9反查, h=0.95) 非空且不超过全量: %r'
       % (None if h is None else len(h)))

    # ── 3. 极性: h=1.0 全保留, h=0.5 约半数 ──
    h1 = SL.query('suika', matchup=1, k=0, heat_weighted=True)
    ck(h1 is not None and len(h1) == 100,
       'h=1.0(最弱对位) → 全保留 100 行(旧实现保留0行): %r'
       % (None if h1 is None else len(h1)))
    h05 = SL.query('suika', matchup=0, k=0, heat_weighted=True)
    ck(h05 is not None and 20 <= len(h05) <= 80,
       'h=0.5 → 保留约半数(实测 %r/100)' % (None if h05 is None else len(h05)))

    # ── 4. le1b 注入: 自动取最弱对位(槽1, h=1.0) 且行数=目标k ──
    wm = L._weakest_matchup('suika')
    ck(wm == 1, '_weakest_matchup 取最大热度槽(1): %r' % (wm,))
    rng = np.random.default_rng(0)
    idx = L.inject_indices('suika', 12, rng)
    ck(idx is not None and len(idx) == 12,
       'inject_indices 传入 matchupy 后返回12行(旧实现恒 None 或全量): %r'
       % (None if idx is None else len(idx)))
    ck(idx is not None and set(int(x) for x in idx) <= set(
        int(x) for x in (h1 if h1 is not None else [])),
       '注入行全部来自热度过滤后的集合(不是全量)')

    # ── 5. 20% 硬钳 ──
    for ratio, want_max in ((0.2, 12), (0.5, 12), (1.0, 12)):
        L.INJECT_RATIO = ratio
        got = L.inject_count(64)
        ck(got <= want_max, 'ratio=%.1f → 注入 %d 行 ≤ 上限 %d(20%%批)'
           % (ratio, got, want_max))
    L.INJECT_RATIO = 0.0
    ck(L.inject_count(64) == 0, 'ratio=0(默认关) → 0 行')
finally:
    SL.OUT_DIR = _orig_out
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)

# ── 6. 真实产物前提核对(沙箱无产物时跳过): heat 键经映射后应落在 mid 空间 ──
_prod = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), 'data', 'situations')
if os.path.isdir(_prod) and os.listdir(_prod):
    for _ch in ('reimu', 'marisa', 'suika'):
        _p = os.path.join(_prod, '%s_index.npz' % _ch)
        if not os.path.exists(_p):
            continue
        _d = np.load(_p, allow_pickle=True)
        _mid = set(int(x) for x in _d['matchup'])
        _heat = json.loads(str(_d['meta'])).get('heat', {})
        _raw_keys = set(int(k) for k in _heat)
        _mapped = {r2p.get(k, k) for k in _raw_keys}
        ck(bool(_mapped & _mid),
           '%s 真实产物: heat 键映射后与 mid 池槽有交集 %s→%s'
           % (_ch, sorted(_raw_keys)[:4], sorted(_mapped)[:4]))
else:
    print('  SKIP  真实产物不在(沙箱) — 语义段已用合成索引验完')

print()
print('==== %d PASS / %d FAIL ====' % (N - BAD, BAD))
sys.exit(1 if BAD else 0)
