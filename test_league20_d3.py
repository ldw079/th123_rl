# -*- coding: utf-8 -*-
"""D3'(R65) league20 配对测试 — 构建/分配/种子/启动校验全链.

覆盖:
  1. league20_opps: 周期组成(主角色块×W含镜像 + league17 + COM尾)/
     确定性/focus排除league
  2. league_alloc: 3角色3actor逐位回归锚 + 泛化和恒 + 余量按胜率权重
     (弱角色多拿练习位)
  3. seed_league_pool: 维度守卫拒收/缺档拒收/幂等跳过/refresh重种/
     v-pi成对落盘(先v=配对提交标记)
  4. build_opp_cycle: fleet池根注入(校验与运行时同池) + 非严格模式
     池空位降级跳过(league未种齐不炸actor) + 严格模式保留SystemExit
  5. 贯通: 种下的档过actor侧_pool_snapshot_ok(维度守卫同判据)
"""
import glob
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

from fleet_supervisor import league_alloc
from league import league20_opps
from tools.seed_league_pool import seed_league_pool
from train_tm import CHAR_LIBS, _pool_snapshot_ok, build_opp_cycle

FOCUS = ('reimu', 'marisa', 'suika')
PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def fake_model(store, ch, delta=0):
    """临时store里造一个假生产模型(W2宽度=宏数+delta)."""
    n = len(CHAR_LIBS[ch]['macros'])
    src = os.path.join(store, 'model_ppo_%s.npz' % ch)
    np.savez(src, W2=np.zeros((1, n + delta), dtype=np.float32))
    np.savez(src.replace('.npz', '_v.npz'), W2=np.zeros((1, 1)))
    return src


def main():
    # --- 1. league20_opps 组成 ---
    opps = league20_opps('reimu')
    ok(len(opps) == 3 * 3 + 17 + 1, "周期长27(主×3块+league17+COM)")
    ok(all(opps.count(c) == 3 for c in FOCUS), "主角色块各3位(镜像在内)")
    league_chars = [c for c in CHAR_LIBS if c not in FOCUS]
    ok(all(c in opps for c in league_chars), "17个league角色全在位")
    ok(opps[-1] == 'COM', "COM在尾")
    ok(league20_opps('suika') == opps, "构建确定(与视角角色无关)")

    # --- 2. league_alloc 泛化 ---
    ok(league_alloc(3) == {'reimu': 1, 'marisa': 1, 'suika': 1},
       "3角色3actor逐位回归(与原硬编码行为相等)")
    ok(league_alloc(6) == {'reimu': 2, 'marisa': 2, 'suika': 2},
       "6actor=每角色保底2")
    st = {'reimu@a': [0, 10], 'marisa@b': [10, 0], 'suika@c': [10, 0]}
    ok(league_alloc(4, stats=st) == {'reimu': 2, 'marisa': 1, 'suika': 1},
       "余量按胜率权重(reimu全败→多拿练习位)")
    five = ('a', 'b', 'c', 'd', 'e')
    a5 = league_alloc(7, chars=five)
    ok(sum(a5.values()) == 7 and all(v >= 1 for v in a5.values()),
       "N角色泛化: 和恒且保底1 (%s)" % a5)

    # --- 3/5. seed_league_pool + 守卫贯通 ---
    tmp = tempfile.mkdtemp(prefix="d3_seed_")
    try:
        fake_model(tmp, 'alice', delta=0)      # 合法
        fake_model(tmp, 'aya', delta=1)        # 宏数不符 → 拒收
        # 其余league角色缺模型档 → 拒收
        seeded, skipped, rejected = seed_league_pool(tmp, FOCUS, verbose=False)
        ok(seeded == ['alice'], "只种合法档(alice)")
        ok(any('aya' in r and '宏数不符' in r for r in rejected)
           and len(rejected) == 16, "维度守卫+缺档拒收16个(不中断)")
        d = os.path.join(tmp, 'fleet', 'pool', 'alice')
        pi = [f for f in glob.glob(os.path.join(d, 'seed_*.npz'))
              if not f.endswith('_v.npz')]
        ok(len(pi) == 1, "种子落盘1个pi档")
        ok(os.path.exists(pi[0].replace('.npz', '_v.npz')),
           "v-pi成对落盘")
        ok(_pool_snapshot_ok(pi[0], len(CHAR_LIBS['alice']['macros'])),
           "贯通: 种下的档过actor侧维度守卫")
        seeded2, skipped2, _r = seed_league_pool(tmp, FOCUS, verbose=False)
        ok(seeded2 == [] and skipped2 == ['alice'], "幂等: 二跑跳过")
        seed_league_pool(tmp, FOCUS, refresh=True, verbose=False)
        ok(len(glob.glob(os.path.join(d, 'seed_*.npz'))) == 2,
           "refresh重种(新时间戳档)")

        # --- 4. build_opp_cycle fleet根注入 + 严格性 ---
        cyc = build_opp_cycle(['alice', 'aya', 'COM'],
                              pool_root=os.path.join(tmp, 'fleet', 'pool'),
                              strict=False)
        ok(cyc == [('alice', None), ('COM', None)],
           "fleet池根校验: 种过的alice保留, 池空的aya降级跳过, COM保留")
        try:
            build_opp_cycle(['alice', 'aya'],
                            pool_root=os.path.join(tmp, 'fleet', 'pool'),
                            strict=True)
            ok(False, "严格模式应SystemExit")
        except SystemExit:
            ok(True, "严格模式保留SystemExit语义(单实例误配置响亮失败)")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
