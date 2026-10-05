# -*- coding: utf-8 -*-
"""数据清理: 删除呆立尾巴的数据集, 修剪幻影期开头。"""

import os
import shutil
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    bad = os.path.join(BASE, "data", "bc_run_20260902_111635")
    if os.path.isdir(bad):
        shutil.rmtree(bad)
        print("已删除(呆立尾巴):", os.path.basename(bad))
    d = os.path.join(BASE, "data", "bc_run_20260902_111258")
    fx = os.path.join(d, "frames.npy")
    fa = os.path.join(d, "actions.npy")
    if os.path.exists(fx):
        X = np.load(fx)
        Y = np.load(fa)
        np.save(fx, X[350:])
        np.save(fa, Y[350:])
        print("已修剪幻影期: %d -> %d 样本" % (len(X), len(X) - 350))


if __name__ == "__main__":
    main()
