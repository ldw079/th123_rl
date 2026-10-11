# -*- coding: utf-8 -*-
"""R44: 六新角色模型文件构建 — init_fresh → STORE。

PPOTrainer 的 n_side=5N+CORE_DIMS / n_out=N(N=当前宏库宏数); 网络规模
与三现役同构(共享conv主干+侧路径+对手子网络+预测头)。已存在则跳过(幂等)。
R65(D3'): n_side原硬编码"+308"是CORE_DIMS变更的漏网常量(F5 308→316,
B 316→330两次都没同步到本工具; 常量横扫SOP的漏网面) — 改为
FeatureBuilder.CORE_DIMS派生随库自动正确; 同批重建17角色模型
(旧档66宏/308核=init_fresh未训练随机网, 重建无损)。
用法: python tools/build_newchar_models.py [--force]
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
NEW = ['sakuya', 'patchouli', 'yuyuko', 'reisen', 'komachi', 'tenshi',
       # R45: 剩余11角色
       'alice', 'youmu', 'remilia', 'yukari', 'aya', 'iku', 'sanae',
       'cirno', 'meiling', 'utsuho', 'suwako']

from train_tm import CHAR_LIBS  # noqa: E402
from feat_builder import FeatureBuilder  # noqa: E402
from ppo import PPOTrainer  # noqa: E402

force = '--force' in sys.argv
for ch in NEW:
    lib = CHAR_LIBS[ch]
    n = len(lib['macros'])
    n_side = 5 * n + FeatureBuilder.CORE_DIMS   # R65: 派生非硬编码
    pi = os.path.join(STORE, 'model_ppo_%s.npz' % ch)
    vv = os.path.join(STORE, 'model_ppo_%s_v.npz' % ch)
    if os.path.exists(pi) and not force:
        print('%-11s 已存在(跳过): %s' % (ch, pi))
        continue
    t = PPOTrainer(n_side=n_side, n_out=n)
    t.init_fresh(3 * 60 * 80)   # 视觉栈14400(与三现役同构)
    t.save(pi, vv)
    sz = os.path.getsize(pi) / 1e6
    print('%-11s 构建完成: N=%d n_side=%d pi=%.1fMB v=%.1fMB'
          % (ch, n, n_side, sz, os.path.getsize(vv) / 1e6))

# 宏计数同步(零初始化满额 — 全新宏从满额配额起步, 与reimu事故后
# 从零重训时同款)
import numpy as np  # noqa: E402
for ch in NEW:
    n = len(CHAR_LIBS[ch]['macros'])
    mc = np.full(n, 150, dtype=np.int64)
    names = CHAR_LIBS[ch]['names']
    for i, nm in enumerate(names):
        if nm in CHAR_LIBS[ch]['sc']:
            mc[i] = 0    # SC宏零计数(sc门控管可用性, 不靠配额)
    p = os.path.join(STORE, 'macro_counts_%s.npy' % ch)
    if os.path.exists(p) and not force:
        print('宏计数已存在(跳过):', ch)
        continue
    np.save(p, mc)
    print('%-11s 宏计数: %d槽(SC宏%d个零计数)' % (ch, n,
                                              int((mc == 0).sum())))
print('全部完成')
