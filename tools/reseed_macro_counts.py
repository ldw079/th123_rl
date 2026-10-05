# -*- coding: utf-8 -*-
"""死招事故后果处置(第六轮§2.2; 从零审查D13加固):
- 受影响集=规范化器导出的NORMALIZED_AFFECTED(精确口径, 替代宽口径)
- 训练器在跑时拒绝(mtime探测, --force跳过) — 原版会被下局内存副本静默回滚
- 写前备份.bak + 原子落盘; 支持--suffix实验分支
用法: python tools/reseed_macro_counts.py [--dry] [--force] [--suffix _exp]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np  # noqa: E402
import macros as mc  # noqa: E402
import macros_marisa as mm  # noqa: E402
import macros_suika as ms  # noqa: E402

STORE = r"D:\temp\th123_models"
LIBS = {"reimu": mc.MACROS, "marisa": mm.MACROS_MARISA, "suika": ms.MACROS_SUIKA}
AFFECTED = {"reimu": mc.NORMALIZED_AFFECTED,
            "marisa": mm.NORMALIZED_AFFECTED,
            "suika": ms.NORMALIZED_AFFECTED}


def main():
    dry = "--dry" in sys.argv
    force = "--force" in sys.argv
    suffix = ""
    if "--suffix" in sys.argv:
        suffix = sys.argv[sys.argv.index("--suffix") + 1]
    # D13: 训练器活跃探测(模型60s内被写过=在跑, 重播种会被内存副本回滚)
    for ch in LIBS:
        p = os.path.join(STORE, "model_ppo_%s%s.npz" % (ch, suffix))
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < 60 \
                and not force:
            print("[拒绝] %s 模型60s内有写入(训练器在跑?) — 先停训练或--force"
                  % ch)
            return 1
    for ch, lib in LIBS.items():
        aff = AFFECTED[ch]
        path = os.path.join(STORE, "macro_counts_%s%s.npy" % (ch, suffix))
        if not os.path.exists(path):
            print("[%s] 无计数文件: %s" % (ch, path))
            continue
        counts = np.load(path)
        idxs = [i for i, m in enumerate(lib) if m[0] in aff and i < len(counts)]
        print("[%s] 精确受影响%d个: %s" % (ch, len(aff), sorted(aff)[:8]))
        if dry:
            print("  dry: 将清零 idx=%s" % idxs)
            continue
        # D13: 备份(可回滚)
        np.save(path + ".bak", counts)
        for i in idxs:
            counts[i] = 0
        tmp = path + ".tmp.npy"
        np.save(tmp, counts)
        os.replace(tmp, path)
        print("  备份.bak+原子落盘: 清零%d个" % len(idxs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
