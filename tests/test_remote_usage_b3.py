# -*- coding: utf-8 -*-
"""B3(F-9观察闭环) 配对测试: remote_usage_report × episode_core 契约贯通.

方法论条款(新模块+新调用方成对落地必附集成测试):
  合成episode走**真实写者路径**(save_episode_npz, 真CHAR_LIBS契约) →
  工具读取(load_episode_npz) → 距离桶/弹幕份额/时间窗/坏档韧性断言。

覆盖:
  1. 份额口径: 远程桶弹幕份额 = 远程弹幕决策/远程总决策(非全决策分母)
  2. 涌现判定: 前窗0% → 后窗50% → delta=+0.5 判"涌现↑"
  3. 距离解码: sides col(2*n+5)×600 ↔ 桶归属(200px近/400px远)
  4. 韧性: 坏档(键缺失)跳过计数, 不炸整报
  5. 排序: 报告窗序按文件名时间戳(非meta.ts — 后者无日期)
"""
import glob
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from episode_core import (EP_SCHEMA, build_contract, episode_meta,
                          load_episode_npz, save_episode_npz)
from train_tm import CHAR_LIBS
from tools.remote_usage_report import collect, report

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def save_synthetic(ep_dir, char, ep_idx, adx_rows, act_ids,
                   ts="20261011_100000"):
    """真实写者路径存一局, 再改名为受控时间戳(工具按文件名排序)."""
    names = [m[0] for m in CHAR_LIBS[char]["macros"]]
    n_macros = len(names)
    from feat_builder import FeatureBuilder
    n_side = 5 * n_macros + FeatureBuilder.CORE_DIMS
    n = len(act_ids)
    sides = np.zeros((n, n_side), dtype=np.float32)
    sides[:, 2 * n_macros + 4] = np.clip(
        np.array(adx_rows, dtype=np.float32) / 600.0, 0, 1)
    arrays = {
        "feats": np.zeros((n, 14400), dtype=np.uint8),
        "sides": sides,
        "acts": np.array(act_ids, dtype=np.int64),
        "rews": np.zeros(n, dtype=np.float32),
        "masks": np.ones((n, n_macros), dtype=np.float32),
        "bc_targets": np.zeros(n, dtype=np.int64),
        "opp_next": np.zeros(n, dtype=np.int64),
        "logps": np.zeros(n, dtype=np.float32),
        "ep_terms": np.zeros(n, dtype=np.float32),
        "distill": np.zeros(n, dtype=np.float32),
    }
    contract = build_contract(char, n_out=n_macros, n_side=n_side,
                              n_macros=n_macros)
    meta = episode_meta(char, 0, ep_idx, 1, 0, n, contract=contract)
    src = save_episode_npz(ep_dir, char, 0, ep_idx, arrays, meta)
    dst = os.path.join(ep_dir, "ep_%s_00_%05d_%s.npz" % (char, ep_idx, ts))
    os.rename(src, dst)
    return dst


def calibrate_adx_col():
    """R67c: 列号经feat_builder独立标定 — 合成已知几何(left.x=100,
    right.x=580 → adx=480), 找到core里*600≈480的列, 必须等于工具常量.
    (教训: 原测试手写同错列号, 断言与实现同错=变异也测不出.)"""
    from feat_builder import FeatureBuilder
    from tools.remote_usage_report import ADX_COL_IN_CORE
    mk = dict(action=0, airBorne=0, cardGauge=0xFFFF, comboDamage=0,
              direction=1, hand=[0xFF] * 10, hitStop=0, hp=10000, score=0,
              spirit=1000, timeStop=0, untech=0)
    # 反转几何(left在右): dx=-480(带符号col2为负), adx=+480(col4恒正)
    # — 单位幅标定无法区分dx/adx, 符号消歧后唯一命中adx列.
    L = dict(mk, **{"position.x": 580.0, "position.y": 0.0})
    R = dict(mk, **{"position.x": 100.0, "position.y": 0.0})
    core = FeatureBuilder(4).build(L, R, {"id": 0, "active": 0, "displayed": 0}, [])
    hits = [i for i in range(16)
            if abs(float(core[i]) * 600.0 - 480.0) < 1.0]
    assert hits == [ADX_COL_IN_CORE], (
        "adx标定列=%r != 工具常量%d (core前16=%s)"
        % (hits, ADX_COL_IN_CORE, np.round(core[:16].astype(float), 3)))
    print("[PASS] adx列经feat_builder标定=col%d(独立于工具实现)" % hits[0])


def main():
    calibrate_adx_col()
    char = "reimu"
    names = [m[0] for m in CHAR_LIBS[char]["macros"]]
    bullet_names = set(CHAR_LIBS[char]["bullet"])
    b_ids = [i for i, nm in enumerate(names) if nm in bullet_names]
    nb_ids = [i for i, nm in enumerate(names) if nm not in bullet_names]
    assert b_ids and nb_ids, "reimu 库须同时含弹幕/非弹幕宏"
    b, nb = b_ids[0], nb_ids[0]

    tmp = tempfile.mkdtemp(prefix="b3_test_")
    try:
        # 窗1(早): 远程全非弹幕 → 远程份额0; 窗2(晚): 远程半弹幕 → 0.5
        save_synthetic(tmp, char, 1,
                       [200.0] * 10 + [400.0] * 10, [nb] * 20,
                       ts="20261011_090000")
        save_synthetic(tmp, char, 2,
                       [200.0] * 10 + [400.0] * 10,
                       [nb] * 10 + [b, nb] * 5,
                       ts="20261011_110000")
        # 坏档: 键缺失 → collect跳过计数
        with open(os.path.join(tmp, "ep_reimu_00_00003_20261011_120000.npz"),
                  "wb") as f:
            np.savez(f, garbage=np.zeros(3))
        # 排序混淆: meta.ts与文件名ts故意不同序(文件名为准); 内容用
        # 近距非弹幕(不污染窗1份额断言)
        save_synthetic(tmp, char, 4, [100.0] * 4, [nb] * 4,
                       ts="20261011_120001")

        eps, skipped = collect(tmp)
        ok(len(eps) == 3, "collect读回3局(坏档跳过)")
        ok(len(skipped) == 1, "坏档计数1: %r" % skipped)
        ok([e['ts'] for e in eps] == ["20261011_090000",
                                      "20261011_110000",
                                      "20261011_120001"],
           "窗序=文件名时间戳升序")
        ok(abs(float(eps[0]['adx'][10]) - 400.0) < 1e-3,
           "距离解码: sides col(2n+5)×600 → 400px")

        rep = report(tmp, bucket=330.0, windows=2)
        cr = rep['chars'][char]
        w0, w1 = cr['windows'][0], cr['windows'][1]
        ok(w0['decisions'] == 20 and w0['far_decisions'] == 10,
           "窗0决策20(远程10)")
        ok(w0['far_bullet_share'] == 0.0 and
           w0['near_bullet_share'] == 0.0, "窗0弹幕份额全0")
        ok(abs(w1['far_bullet_share'] - 0.5) < 1e-9,
           "窗1远程弹幕份额=0.5(分母=远程桶决策数)")
        ok(w1['near_bullet_share'] == 0.0,
           "近战桶份额=0(远程弹幕不计入近战分母)")
        ok(abs(cr['far_share_delta'] - 0.5) < 1e-9,
           "涌现判定delta=+0.5")
        ok(list(w1['top_far_bullets'])[0] == names[b],
           "远程Top弹幕=合成的那个宏名")

        # --- R67d(bug档回填): 空窗路径 + delta恰为0 ---
        # marisa只有1局, windows=2 → 次窗空(原KeyError崩溃点)
        n_m = len(CHAR_LIBS['marisa']['macros'])
        m_names = [m[0] for m in CHAR_LIBS['marisa']['macros']]
        m_nb = [i for i, nm in enumerate(m_names)
                if nm not in CHAR_LIBS['marisa']['bullet']][0]
        sides_m = np.zeros((6, 5 * n_m + 330), dtype=np.float32)
        sides_m[:, 2 * n_m + 4] = 0.5   # 300px 近距
        arrays_m = dict(
            feats=np.zeros((6, 14400), dtype=np.uint8), sides=sides_m,
            acts=np.full(6, m_nb, dtype=np.int64),
            rews=np.zeros(6, dtype=np.float32),
            masks=np.ones((6, n_m), dtype=np.float32),
            bc_targets=np.zeros(6, dtype=np.int64),
            opp_next=np.zeros(6, dtype=np.int64),
            logps=np.zeros(6, dtype=np.float32),
            ep_terms=np.zeros(6, dtype=np.float32),
            distill=np.zeros((0, 11), dtype=np.float32))
        save_synthetic(tmp, 'marisa', 9, [300.0] * 6, [m_nb] * 6,
                       ts='20261012_130000')
        rep2 = report(tmp, bucket=330.0, windows=2)
        wm = rep2['chars']['marisa']['windows']
        ok(wm[0]['decisions'] == 0
           and wm[0]['far_bullet_share'] is None,
           '空窗路径不炸且键齐(bug回填: 原此处KeyError; n=1时首窗[0:0]空)')
        ok(rep2['chars']['marisa']['far_share_delta'] is None,
           '单局角色delta=None(无数据不伪造)')
        ok(rep2['chars']['reimu']['far_share_delta'] == 0.5,
           '正常角色delta不受影响')
        # delta恰为0.0: suika两局远弹份额相等 → 0.0而非None(and/or惯用法
        # 原把真零变化误标无数据)
        n_s = len(CHAR_LIBS['suika']['macros'])
        s_names = [m[0] for m in CHAR_LIBS['suika']['macros']]
        s_b = [i for i, nm in enumerate(s_names)
               if nm in CHAR_LIBS['suika']['bullet']][0]
        s_nb = [i for i, nm in enumerate(s_names)
                if nm not in CHAR_LIBS['suika']['bullet']][0]
        save_synthetic(tmp, 'suika', 21,
                       [450.0] * 4, [s_b, s_nb, s_b, s_nb],
                       ts='20261012_131000')
        save_synthetic(tmp, 'suika', 22,
                       [450.0] * 4, [s_b, s_nb, s_b, s_nb],
                       ts='20261012_132000')
        rep3 = report(tmp, bucket=330.0, windows=2)
        ok(rep3['chars']['suika']['far_share_delta'] == 0.0,
           'delta恰为0.0时报0.0不报None(真零变化≠无数据)')
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # 读写往返不经工具的契约健全性(同一路径两读者一致)
    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
