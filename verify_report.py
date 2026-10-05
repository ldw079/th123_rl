# -*- coding: utf-8 -*-
"""验证分析报告的关键声明(P0-1/P0-2/P0-3/P0-5)"""
import sys
import os
import zipfile

import numpy as np

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
os.chdir(r"%USERPROFILE%\Desktop\workplace\th123_rl")

out = []

def w(s):
    out.append(str(s))

# === P0-1: 熵梯度符号 ===
w("=== P0-1: 熵梯度符号验证 ===")
from ppo import _softmax
rng = np.random.default_rng(42)
z = rng.standard_normal((1, 5)).astype(np.float32)
P = _softmax(z)
H = float(-(P * np.log(P)).sum())
eg = P * (np.log(np.clip(P, 1e-8, 1.0)) +
          (-(np.log(np.clip(P, 1e-8, 1.0)) * P).sum(1, keepdims=True)))
eps = 1e-4
tg = []
for j in range(5):
    zp = z.copy(); zp[0, j] += eps
    Pp = _softmax(zp); Hp = float(-(Pp * np.log(Pp)).sum())
    zm = z.copy(); zm[0, j] -= eps
    Pm = _softmax(zm); Hm = float(-(Pm * np.log(Pm)).sum())
    tg.append((Hp - Hm) / (2 * eps))
tg = np.array(tg)
w("H = %.5f" % H)
w("code ent_grad: %s" % np.round(eg[0], 6))
w("true dH/dz:    %s" % np.round(tg, 6))
w("ent_grad == -dH/dz: %s" % np.allclose(eg[0], -tg, atol=1e-4))

# === P0-2: turn_recency写入错误下标 ===
w("\n=== P0-2: turn_recency下标验证 ===")
from feat_builder import FeatureBuilder
from train_tm import CHAR_LIBS
for char, lib in CHAR_LIBS.items():
    n = len(lib["macros"])
    fb = FeatureBuilder(n)
    # 模拟数据
    left = {"position.x": 600.0, "position.y": 100.0, "direction": 1,
            "airBorne": False, "hp": 10000, "spirit": 1000, "cardGauge": 250,
            "score": 0, "action": 0,
            "hand": b"\xd2\x01\xff\xff\xff\xff\xff\xff\xff\xff",
            "comboDamage": 0, "untech": 0, "timeStop": 0, "hitStop": 0}
    right = dict(left); right["position.x"] = 800.0; right["action"] = 250
    weather = {"active": 5, "timer": 500}
    bullets = []
    core = fb.build(left, right, weather, bullets)
    # 模拟train_tm的写入
    write_idx = 2 * n + 34 + 1
    w("%s(n=%d): 写入core[%d](越界=%s) 正确应为core[33]" %
      (char, n, write_idx, write_idx >= len(core)))
    # 验证core[33]当前值(应为0, 留给外部填)
    w("  core[33]当前=%.2f(应由外部写入turn_recency)" % core[33])
    # 验证write_idx处当前是什么特征
    w("  core[%d]当前=%.2f(被污染的特征)" % (write_idx, core[write_idx]))

# === P0-3: TTI单位 ===
w("\n=== P0-3: TTI单位验证 ===")
from threat import threat_predict
# 弹在500外以-10/帧速度接近, 自身静止在x=600
tti, inc = threat_predict(600.0, 100.0, [(0, 500.0, 100.0, -10.0, 0.0)], 60)
w("弹距100, 速度-10/帧 → tti=%.1f(帧) incoming=%d" % (tti or -1, inc))
w("  若按秒比较: tti < 0.3 = %s" % ((tti or 999) < 0.3))
w("  若按帧比较: tti < 18  = %s" % ((tti or 999) < 18))

# === P0-4b: y>200过滤 ===
w("\n=== P0-4b: y>200过滤验证 ===")
w("游戏y轴: 地面=0, 向上为正")
w("threat.py第16行: if y > 200: continue")
w("→ 高度>200的弹(高空火力)被排除")
tti2, inc2 = threat_predict(600.0, 100.0,
                              [(0, 550.0, 250.0, -10.0, 0.0)], 60)
w("高度250弹存在时: incoming=%d(被过滤则为0)" % inc2)

# === P0-5: 文件损坏 ===
w("\n=== P0-5: distill文件损坏验证 ===")
p = r"D:\temp\th123_models\distill_data_reimu.npz"
if os.path.exists(p):
    try:
        zf = zipfile.ZipFile(p)
        bad = zf.testzip()
        w("testzip结果: %s" % (bad or "通过"))
    except Exception as e:
        w("打开失败: %s" % e)
else:
    w("文件不存在")

# === P2-6: reimu j2B vs jB ===
w("\n=== P2-6: reimu j2B vs jB ===")
import importlib
m = importlib.import_module("macros")
for name, script in m.MACROS:
    if name in ("jB", "j2B"):
        w("  %s: %s" % (name, script))
w("输入相同: %s" % (
    dict(m.MACROS)["jB"] == dict(m.MACROS)["j2B"]))

print("\n".join(out))
