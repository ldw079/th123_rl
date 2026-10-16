# -*- coding: utf-8 -*-
"""R38 P0-5行为测试(2026-10-14变异漏网补): BC构建必须走对齐器。

变异面: bc_build的`from bc_align import estimate_lag_map, realign,
post_validate`被缩成只导入estimate_lag_map → 旧shard(无ilog)路径
runtime NameError(若执行)或静默跳过对齐 → 状态/输入错位标签复活。
既有测试全绿漏网原因: 无任何测试触达v1对齐路径的依赖完整性。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    # 1. 依赖完整性: build_rows的v1路径按名调用这三个模块级符号 —
    #    变异(截断import)下getattr为None/缺失
    import bc_build
    for fn in ("estimate_lag_map", "realign", "post_validate"):
        check("bc_build.%s可解析" % fn,
              callable(getattr(bc_build, fn, None)))

    # 2. realign语义: 滞后k重排 u16_al[j]=u16[j-k]
    from bc_align import realign
    src = np.arange(1, 101, dtype=np.uint16)
    lag = np.full(100, 3)
    valid = np.ones(100, dtype=bool)
    out = realign(src, lag, valid)
    check("realign滞后3重排", out[10] == src[7] and out[3] == src[0])
    check("realign越界=中性0", out[0] == 0 and out[2] == 0)
    invalid = valid.copy()
    invalid[50:] = False
    out2 = realign(src, lag, invalid)
    check("realign无效帧=0", (out2[50:] == 0).all() and out2[10] == src[7])

    # 3. post_validate契约: 返回(掩码, 通过窗数, 总窗数), 掩码布尔
    from bc_align import post_validate

    class _F(dict):
        pass

    def _frm(x):
        return _F({'position.x': x})
    frames = [(_frm(500.0 + (i % 7)), _frm(700.0), {}, ())
              for i in range(200)]
    m, n_ok, n_tot = post_validate(frames, src[:200],
                                   np.ones(200, dtype=bool))
    check("post_validate契约",
          m.dtype == bool and len(m) == 200
          and isinstance(n_ok, int) and isinstance(n_tot, int)
          and n_tot >= 0 and n_ok <= n_tot)   # 合成往返运动无可靠窗=0窗合法

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
