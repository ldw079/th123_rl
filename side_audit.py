# -*- coding: utf-8 -*-
"""侧输入显著度自审(XRL): W_side 哪些态势维度在驱动决策, 各偏好哪些宏。

纯读 model_ppo.npz, 可在批间随时运行。
运行: <python> side_audit.py [模型路径]
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from macros import MACRO_NAMES, N_MACROS

PPO_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_ppo.npz")

# 侧输入特征名(与 train_rl.py side 构造严格同序; 维度=2*N_MACROS+166)
SIDE_NAMES = (
    ["宏%d" % i for i in range(N_MACROS)] + ["上宏%d" % i for i in range(N_MACROS)]
    + ["灵力", "距离dx", "高度差dy", "接近中", "我方在左", "我在角", "敌在角", "舞台优势",
       "天气", "我HP", "敌HP", "我朝向", "敌朝向", "敌动作ID", "我防御态", "我受击态"]
    + ["敌vx", "敌vy", "我vy", "敌灵力"]
    + ["敌动作桶%d" % i for i in range(8)]
    + ["我带%d" % i for i in range(3)] + ["敌带%d" % i for i in range(3)]
    + ["我滞空", "敌滞空"]
    + ["距离带%d" % i for i in range(4)] + ["高度带%d" % i for i in range(3)]
    + ["近弹有", "近弹dx", "近弹dy", "弹密度"]
    + ["网格%d" % i for i in range(36)]
    + ["TTI", "来袭数"]
    + ["未来15格%d" % i for i in range(18)]
    + ["未来30格%d" % i for i in range(18)]
    + ["天气%d" % i for i in range(22)] + ["天气进度"]
    + ["卡充能", "手牌数"]
    + ["选中灵击札", "选中药水", "选中护符", "选中警醒阵", "选中亚空穴", "选中升天脚",
       "选中妙珠", "选中封印", "选中鬼缚阵", "选中明珠", "选中宝玉", "选中鬼神玉",
       "选中空/未知"]
    + ["持灵击札", "持药水", "持护符", "持警醒阵", "持亚空穴", "持升天脚", "持妙珠",
       "持封印", "持鬼缚阵", "持明珠", "持宝玉", "持鬼神玉"]
    + ["选中卡可用", "敌卡充能", "敌手牌数"]
    + ["情境:防", "情境:攻", "情境:跳", "情境:进", "情境:退", "情境:冲",
       "情境:射", "情境:怠"]
    + ["占据%d" % i for i in range(6)]
    + ["被防反击", "被防跳避", "对空反应", "受压防御", "起身攻击", "起身跳"]
    + ["跳频", "囤牌", "充能", "低灵", "射击"]
    + ["漂移", "样本量"]
    + ["敌角色%d" % i for i in range(22)]
    + ["敌机体reach", "敌机体dash", "敌机体flight", "敌机体zoner"]
)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else PPO_MODEL
    d = np.load(path)
    if "W_side" not in d:
        print("[错误] 模型无 W_side")
        sys.exit(1)
    W = d["W_side"]                     # (N_SIDE, N_MACROS)
    if W.shape[0] != len(SIDE_NAMES):
        print("[错误] W_side 维度 %d 与特征名表 %d 不符(架构变更后需同步 SIDE_NAMES)"
              % (W.shape[0], len(SIDE_NAMES)))
        sys.exit(1)
    print("[模型] W_side %s (侧输入%d维 → %d宏)" % (W.shape, W.shape[0], W.shape[1]))

    imp = np.abs(W).max(axis=1)         # 该特征能撬动的最大 logit 幅度
    order = np.argsort(-imp)

    print("\n==== 显著度 Top 25(特征 → 最大|logit权重|) ====")
    for i in order[:25]:
        prefs = np.argsort(-W[i])[:3]
        pref_s = " ".join("%s%+.2f" % (MACRO_NAMES[m], W[i][m]) for m in prefs)
        print("  %-10s %6.3f → %s" % (SIDE_NAMES[i], imp[i], pref_s))

    # 分组聚合: 宏史/标量/速度灵力/动作桶/位置带/弹幕
    def group_imp(lo, hi, name):
        v = imp[lo:hi]
        print("  %-12s 均值%.3f 峰值%.3f(%s)" % (name, v.mean(), v.max(),
                                              SIDE_NAMES[lo + int(np.argmax(v))]))

    print("\n==== 分组显著度 ====")
    group_imp(0, 2 * N_MACROS, "宏历史")
    group_imp(2 * N_MACROS, 2 * N_MACROS + 16, "核心标量")
    group_imp(2 * N_MACROS + 16, 2 * N_MACROS + 20, "速度/敌灵力(新)")
    group_imp(2 * N_MACROS + 20, 2 * N_MACROS + 28, "敌动作桶(新)")
    group_imp(2 * N_MACROS + 28, 2 * N_MACROS + 43, "位置/距离/高度带")
    group_imp(2 * N_MACROS + 43, 2 * N_MACROS + 85, "弹幕场/TTI")
    group_imp(2 * N_MACROS + 85, 2 * N_MACROS + 121, "未来占据网格")
    group_imp(2 * N_MACROS + 121, 2 * N_MACROS + 144, "天气onehot/进度(新)")
    group_imp(2 * N_MACROS + 144, 2 * N_MACROS + 173, "符卡感知(异卡组泛化13+12)")
    group_imp(2 * N_MACROS + 173, 2 * N_MACROS + 200, "对手建模v2(时空条件化)")
    group_imp(2 * N_MACROS + 200, 2 * N_MACROS + 227, "对阵适应(角色ID+机体属性)")

    # 各宏的侧驱动强度(行上看哪宏被侧输入影响最大)
    col = np.abs(W).max(axis=0)
    print("\n==== 最受侧输入驱动的宏 Top 10 ====")
    for m in np.argsort(-col)[:10]:
        print("  %-8s %.3f" % (MACRO_NAMES[m], col[m]))
    print("\n==== 最不受侧输入驱动的宏 Top 5(疑似盲选, 需关注) ====")
    for m in np.argsort(col)[:5]:
        print("  %-8s %.3f" % (MACRO_NAMES[m], col[m]))


if __name__ == "__main__":
    main()
