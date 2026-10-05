# -*- coding: utf-8 -*-
"""meta往返测试: save→load→断言6字段逐一相等。R13建议。"""
import sys, os, tempfile
import numpy as np
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # 相对路径: 变异沙箱内解析到沙箱树
import ppo

# 设互不相同的值
tr = ppo.PPOTrainer(n_side=100, n_out=10)
tr.init_fresh(ppo.TRUNK_FLAT)
tr._temp = 0.77
tr._beta = 0.0123
tr._bcw = 0.0456
tr._updates = 321
tr._rstd = 2.71
tr._adaptive_lr_scale = 0.42

# save
tp = os.path.join(tempfile.gettempdir(), '_rt_pi.npz')
tv = os.path.join(tempfile.gettempdir(), '_rt_v.npz')
tr.save(tp, tv)

# load到新实例
tr2 = ppo.PPOTrainer(n_side=100, n_out=10)
tr2.init_fresh(ppo.TRUNK_FLAT)
tr2.load(tp, tv)

# 断言
checks = [
    ('_temp', 0.77), ('_beta', 0.0123), ('_bcw', 0.0456),
    ('_updates', 321), ('_rstd', 2.71), ('_adaptive_lr_scale', 0.42),
]
all_pass = True
for name, expected in checks:
    got = getattr(tr2, name, None)
    ok = (got is not None and abs(float(got) - expected) < 1e-5)
    print('  %-22s 期望=%.4f 实际=%.4f %s' % (name, expected,
          float(got) if got is not None else -1, '✓' if ok else '✗'))
    if not ok:
        all_pass = False

os.unlink(tp)
os.unlink(tv)

if all_pass:
    print('\n✓ 往返测试通过 — meta存取一致')
else:
    print('\n✗ 往返测试失败!')
    sys.exit(1)
