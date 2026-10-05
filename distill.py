# -*- coding: utf-8 -*-
"""蒸馏诊断(宏版): 状态 → 宏选择 的可读决策树。

特征: 距离/灵力/贴身/上宏ID/游戏帧 → 宏ID(多类分类)。
运行: <python> distill.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from macros import MACRO_NAMES

DISTILL_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "distill_data.npz")
FEAT_NAMES = ["距离adx", "灵力", "贴身", "上宏ID", "游戏帧",
              "高度差dy", "敌空中", "弹近", "我左", "TTI", "敌在角"]


def main():
    if not os.path.exists(DISTILL_DATA):
        print("[错误] 没有蒸馏数据(先跑几批训练自动收集)")
        sys.exit(1)
    d = np.load(DISTILL_DATA)
    X, Y = Xy = d["X"], d["Y"].astype(int)
    if X.shape[1] != len(FEAT_NAMES):
        print("[提示] 旧格式数据(特征 %d 维), 期望 %d — 新批训练后自动覆盖" % (X.shape[1], len(FEAT_NAMES)))
        return
    use = X[:, 0] >= 0
    X, Y = X[use], Y[use]
    print("[数据] %d 条 (距离均值 %.0f, 灵力均值 %.2f, 贴身率 %.0f%%)"
          % (len(X), X[:, 0].mean(), X[:, 1].mean(), 100 * (X[:, 2] > 0).mean()))
    from sklearn.tree import DecisionTreeClassifier, export_text
    # R38(第九轮审计§2.2): 原报告的是训练集准确率(虚高) — 改80/20留出
    rng = np.random.default_rng(20261003)
    perm = rng.permutation(len(X))
    cut = int(len(X) * 0.8)
    tr, te = perm[:cut], perm[cut:]
    tree = DecisionTreeClassifier(max_depth=4, min_samples_leaf=25, random_state=0)
    tree.fit(X[tr], Y[tr])
    print("[宏分类树] 留出准确率 %.0f%% (训练 %.0f%%)"
          % (100 * tree.score(X[te], Y[te]), 100 * tree.score(X[tr], Y[tr])))
    print(export_text(tree, class_names=MACRO_NAMES, feature_names=FEAT_NAMES, max_depth=4))


if __name__ == "__main__":
    main()
