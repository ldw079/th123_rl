# -*- coding: utf-8 -*-
"""R17 BC库重铺垫: 侧向量core 260→308(对手建模段10: 27→75)。

旧布局: [宏one-hot 2N][core 260], 段10在core[152..178)。
新布局: [宏one-hot 2N][core 308], 段10在core[152..227)。
变换: core[0..152)原位 + 48列零(历史40+资源8, 旧库无此数据=未知)
      + core[152..260)平移+48。宏one-hot段(含换技连段槽)原位不动。
历史特征全零=「无历史信息」语义, 可接受(新训练数据会自然填充)。
"""
import os
import shutil
import sys

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json

import numpy as np

OLD_CORE, NEW_CORE, SEG10_OFF, GROW = 260, 308, 152, 48
BC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'bc')

for fn in sorted(os.listdir(BC_DIR)):
    if not fn.endswith('.npz'):
        continue
    p = os.path.join(BC_DIR, fn)
    d = np.load(p, allow_pickle=False)
    # R38守卫(第九轮审计P0-6): 带layout版本的库是bc_build原生构建的
    # 正确布局 — 本脚本的260→308平移会把它当成旧布局在错误段插零列
    # (suika 658宽曾恰好通过整除断言被腐蚀)。带版本=拒跑。
    try:
        meta = json.loads(str(np.load(p, allow_pickle=True)['meta']))
    except Exception:
        meta = {}
    if isinstance(meta, dict) and meta.get('layout'):
        print("%s 布局%s(原生构建) — 拒绝repad" % (fn, meta['layout']))
        continue
    S = d['S']
    side_old = S.shape[1]
    two_n = side_old - OLD_CORE
    assert two_n > 0 and two_n % 2 == 0, "%s 侧宽%d非旧布局" % (fn, side_old)
    if side_old == two_n + NEW_CORE:
        print("%s 已是R17布局(%d) — 跳过" % (fn, side_old))
        continue
    core = S[:, two_n:]
    assert core.shape[1] == OLD_CORE, "%s core宽%d" % (fn, core.shape[1])
    new_core = np.concatenate(
        [core[:, :SEG10_OFF],
         np.zeros((len(S), GROW), dtype=S.dtype),
         core[:, SEG10_OFF:]], axis=1)
    S_new = np.concatenate([S[:, :two_n], new_core], axis=1)
    bak = p + '.r16.bak'
    if not os.path.exists(bak):
        shutil.copy2(p, bak)
    np.savez(p, X=d['X'], Y=d['Y'], S=S_new, C=d['C'])
    print("%s: %d → %d (备份 %s)" % (fn, side_old, S_new.shape[1],
                                     os.path.basename(bak)))
print("BC库R17重铺垫完成")
