# -*- coding: utf-8 -*-
"""S-7A风格嵌入行为测试(合并终版方案).

PCA拟合确定性/形状; 嵌入16维块结构(PCA8+漂移1+资源差分4+卡组3);
无语料路径返None(不阻塞训练); 组件存取往返。
"""
import os
import sys
import tempfile
from types import SimpleNamespace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

import style_embedding as se                      # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def _fake_model(ctx=None, recent=None, older=None,
                res_full=None, res_low=None):
    return SimpleNamespace(
        ctx=ctx or [[10.0] * 8 for _ in range(9)],
        ctx_total=[80.0] * 9,
        _recent=recent or [1.0] * 8,
        _older=older or [1.0] * 8,
        _res_full=res_full or [5.0, 3.0, 2.0, 1.0],
        _res_low=res_low or [1.0, 2.0, 1.0, 5.0],
        _res_full_tot=11.0,
        _res_low_tot=9.0)


def main():
    rng = np.random.default_rng(11)
    # 1. PCA拟合: 形状+确定性
    X = rng.random((120, 72))
    c1, m1 = se.fit_pca(X, 8)
    c2, m2 = se.fit_pca(X, 8)
    check('PCA形状', c1.shape == (8, 72) and m1.shape == (72,))
    check('PCA确定性', np.array_equal(c1, c2) and np.array_equal(m1, m2))
    # 方差解释: top8对合成低秩语料应高
    Xlow = (rng.random((120, 3)) @ rng.random((3, 72)))
    cl, ml = se.fit_pca(Xlow, 8)
    Xc = Xlow - ml
    evr = float(((Xc @ cl.T) ** 2).sum() / (Xc ** 2).sum())
    check('低秩语料top-8解释率>99%', evr > 0.99, '%.4f' % evr)

    # 2. 组件往返
    tmp = os.path.join(tempfile.mkdtemp(prefix='s7a_'), 'pca.npz')
    se.save_components(c1, m1, tmp)
    c3, m3 = se.load_components(tmp)
    check('组件往返', np.array_equal(c1, c3) and np.array_equal(m1, m3))

    # 3. 嵌入块结构
    emb = se.style_embedding(_fake_model(), np.arange(14) / 14.0,
                             components=c1, mean=m1)
    check('嵌入16维', emb is not None and emb.shape == (16,))
    check('PCA段限幅', (np.abs(emb[:8]) <= 4.0).all())
    check('漂移段非负', emb[8] >= 0 and emb[8] <= 2)
    # 漂移: 分布不同→>0; 相同→0
    same = se.style_embedding(_fake_model(), np.zeros(14),
                              components=c1, mean=m1)
    check('漂移=0(分布相同)', abs(same[8]) < 1e-9)
    diff = se.style_embedding(
        _fake_model(recent=[9, 0, 0, 0, 0, 0, 0, 0],
                    older=[0, 0, 0, 0, 0, 0, 0, 9]),
        np.zeros(14), components=c1, mean=m1)
    check('漂移>0(分布不同)', diff[8] > 1.0, '%.2f' % diff[8])
    # 资源差分方向: 灵满防多-灵空防少 → 段[0]>0
    check('资源差分方向', emb[9] > 0, '%.2f' % emb[9])
    # 卡组段=三分组均值
    b = np.arange(14) / 14.0
    check('卡组段=均值', np.allclose(emb[13:16],
                                   [b[:5].mean(), b[5:10].mean(),
                                    b[10:].mean()], atol=1e-6))

    # 4. 无语料路径(None, 不抛)
    old = se._COMP_PATH
    se._COMP_PATH = os.path.join(tempfile.mkdtemp(), 'none.npz')
    try:
        r = se.style_embedding(_fake_model(), np.zeros(14))
        check('无语料返None', r is None)
    finally:
        se._COMP_PATH = old

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
