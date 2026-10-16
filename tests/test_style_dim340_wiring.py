# -*- coding: utf-8 -*-
"""P2(2026-10-14晚审计): S-7风格维340/341接线测试 — build()→style_embedding
通路此前无测试(组件级12项测的是style_embedding自身, 接线层空缺)。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
_sys_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _sys_root)
import numpy as np
from feat_builder import FeatureBuilder


def _state(i):
    x_l = 100 + (i * 137) % 1000
    left = {
        "position.x": float(x_l), "position.y": float((i * 53) % 400),
        "spirit": 2000 - (i * 97) % 1800, "hp": 10000 - (i * 331) % 9000,
        "airBorne": i % 3 == 0, "direction": 1 if i % 2 else -1,
        "action": (i * 127) % 300, "cardGauge": (i * 371) % 0xFF00,
        "score": i % 3, "hand": bytes([(i + k) % 250 for k in range(10)]),
        "comboDamage": 0, "untech": 0, "timeStop": 0, "hitStop": 0,
        "pose": 0, "poseFrame": 0,
    }
    right = dict(left)
    right.update({
        "position.x": float(1100 - (i * 211) % 950),
        "position.y": float((i * 89) % 350),
        "action": 300 + (i * 53) % 200,
        "direction": -1 if i % 2 else 1,
        "hitStop": 0,
    })
    weather = {"active": 0, "displayed": 0, "timer": 0}
    return left, right, weather, []


def _collect():
    fb = FeatureBuilder(n_macros=22)
    out = []
    for i in range(30):
        l, r, w, b = _state(i)
        fb.update_opp(10 / 62, l, r, w, opp_vx=float((i % 5) - 2))
        out.append(np.asarray(fb.build(l, r, w, b), dtype=np.float64))
    return np.stack(out)


def test_wiring_nonzero_with_corpus():
    """有style_pca语料: 维340/341在多样对手状态序列上应有读数
    (方差>0=真接线; 恒零=断线/静默异常)。"""
    V = _collect()
    assert V.shape == (30, FeatureBuilder.CORE_DIMS)
    v0, v1 = V[:, 340], V[:, 341]
    assert v0.std() > 1e-6 or v1.std() > 1e-6, \
        '风格维340/341恒定: v0.std=%.2e v1.std=%.2e (接线断裂?)' % (
            v0.std(), v1.std())
    assert np.all(np.abs(v0) <= 1.0 + 1e-6)
    assert np.all(np.abs(v1) <= 1.0 + 1e-6)   # clip(-4,4)/4范围


def test_wiring_graceful_without_corpus():
    """无语料(语料路径指向不存在): 归零不崩, 不留静默异常气味。"""
    import style_embedding as se
    _orig = se._COMP_PATH
    se._COMP_PATH = _os.path.join(_sys_root, 'data', '_no_such_pca.npz')
    try:
        V = _collect()
        assert np.all(V[:, 340] == 0.0)
        assert np.all(V[:, 341] == 0.0)
    finally:
        se._COMP_PATH = _orig
    # 恢复后立即有读数(无跨测试状态残留)
    V2 = _collect()
    assert V2[:, 340].std() > 1e-6 or V2[:, 341].std() > 1e-6


def test_wiring_loud_on_corrupt_corpus():
    """损坏语料(可load但形状错): 首错打印, 特征归零不崩(区分于无语料)。"""
    import style_embedding as se
    import tempfile
    # 构造形状错误的components档
    with tempfile.NamedTemporaryFile(suffix='.npz', delete=False) as f:
        np.savez(f, components=np.zeros((3, 5), dtype=np.float32),
                 mean=np.zeros(5, dtype=np.float32))
        bad = f.name
    _orig = se._COMP_PATH
    se._COMP_PATH = bad
    import io as _io
    import contextlib
    buf = _io.StringIO()
    try:
        fb = FeatureBuilder(n_macros=22)
        with contextlib.redirect_stdout(buf):
            for i in range(30):
                l, r, w, b = _state(i)
                fb.update_opp(10 / 62, l, r, w, opp_vx=1.0)
                fb.build(l, r, w, b)
        # 首错响亮(S-7风格段异常) 且不重复刷屏
        n_err = buf.getvalue().count('S-7风格段异常')
        assert n_err >= 1, '损坏语料应首错打印'
        assert n_err <= 1, '首错后应静默(防刷屏), 实际%d次' % n_err
    finally:
        se._COMP_PATH = _orig
        _os.remove(bad)


if __name__ == '__main__':
    for fn in [test_wiring_nonzero_with_corpus,
               test_wiring_graceful_without_corpus,
               test_wiring_loud_on_corrupt_corpus]:
        fn()
        print('✓', fn.__name__)
    print('test_style_dim340_wiring: 全部通过')
