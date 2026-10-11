# -*- coding: utf-8 -*-
"""R16§3门禁行为测试: 每个特征段至少有一个非恒定维(32%结构性死区→红灯)。
方法: 构造覆盖对局多样状态的合成序列, 连续build()收集全维向量,
按段表逐段断言"至少1维在序列上有方差"。
段表与feat_builder.build()的o推进严格对应(改动段宽时须同步本表)。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # 相对路径: 变异沙箱内解析到沙箱树
import numpy as np
from feat_builder import FeatureBuilder

# (名称, 起始, 宽度) — 与build()各段o += 顺序一致
# R17: 段10对手建模27→75(历史40+资源8), 其后段整体+48
# R57(第十八轮2.5): 14i宽6→2(hitStop/低血警报写点自R49起被pose尾部
# 覆盖=死特征已删; 对手滞空位改下段位), 新增14j pose块(原静默覆盖区入账)
SEGMENTS = [
    ("1核心标量", 0, 16), ("2动作类", 16, 16), ("3朝向", 32, 2),
    ("4位置带", 34, 14), ("5速度资源", 48, 4), ("6弹幕威胁", 52, 6),
    ("7威胁网格", 58, 36), ("8未来占据", 94, 36), ("9卡牌感知", 130, 22),
    ("10对手建模", 152, 75), ("11对局适应", 227, 26), ("12势函数", 253, 4),
    ("13擦弹防守", 257, 10), ("14a弹速统计", 267, 8), ("14b动作历史", 275, 8),
    ("14c密度梯度", 283, 6), ("14e我方空间", 289, 3), ("14f动量", 292, 3),
    ("14g资源差", 295, 3), ("14h威胁补充", 298, 4), ("14i状态计时", 302, 2),
    ("14j pose块", 304, 4),
]


def _state(i):
    """合成第i拍状态: 位置/血量/动作/弹幕全方位变化。"""
    x_l = 100 + (i * 137) % 1000
    x_r = 1100 - (i * 211) % 950
    left = {
        "position.x": float(x_l), "position.y": float((i * 53) % 400),
        "spirit": 2000 - (i * 97) % 1800, "hp": 10000 - (i * 331) % 9000,
        "airBorne": i % 3 == 0, "direction": 1 if i % 2 else -1,
        "action": (i * 127) % 1024, "cardGauge": (i * 371) % 0xFF00,
        "score": i % 3, "hand": bytes([(i + k) % 250 for k in range(10)]),
        "comboDamage": (i * 211) % 3000 if i % 4 else 0,
        "untech": (i * 17) % 40 if i % 5 else 0,
        "timeStop": 5 if i % 11 == 0 else 0, "hitStop": (i * 7) % 12,
        # R57: pose块(14j)活性覆盖 — 蓄力/段内进度变化
        "pose": (i * 3) % 30, "poseFrame": (i * 11) % 100,
    }
    right = dict(left)
    right.update({
        "position.x": float(x_r), "position.y": float((i * 89) % 350),
        "spirit": 200 + (i * 149) % 1800, "hp": 8000 - (i * 277) % 7000,
        "airBorne": i % 4 == 1, "direction": -1 if i % 2 else 1,
        # R21: 150系=立防(XML权威; 旧110实为受击空中) → 防御倾向覆盖
        "action": 150 + (i % 4) if i % 7 == 0 else (i * 173) % 1024,
        "cardGauge": (i * 443) % 0xFF00,
        "score": (i + 1) % 3, "hitStop": (i * 13) % 12,
        # R57: 下段位覆盖 — i%5∈{0,1}时对手出2A/2C(303/412)蹲防位翻转
        "pose": (i * 7) % 30, "poseFrame": (i * 13) % 100,
    })
    if i % 5 in (0, 1):
        right["action"] = 303 if i % 5 == 0 else 412
    weather = {"active": (i * 7) % 22, "displayed": (i * 5) % 22,
               "timer": (i * 61) % 999}
    n_b = (i * 5) % 14
    bullets = [(1, x_l + 300 - i * 40 + k * 25, 100.0 + k * 30,
                -8.0 - k, 1.0 * (i % 3 - 1)) for k in range(n_b)]
    return left, right, weather, bullets


fb = FeatureBuilder(n_macros=22)
vecs = []
for i in range(24):
    l, r, w, b = _state(i)
    vecs.append(np.asarray(fb.build(l, r, w, b), dtype=np.float64))
    # 决策拍间推进对手模型(对手建模段需要历史才非恒定)
    fb.update_opp(10 / 62, l, r, w, opp_vx=float((i % 5) - 2))
V = np.stack(vecs)
assert V.shape == (24, fb.CORE_DIMS), '形状%s' % (V.shape,)

dead = []
for name, off, wd in SEGMENTS:
    seg_var = V[:, off:off + wd].var(axis=0).max()
    if seg_var < 1e-6:
        dead.append((name, off, wd))
    else:
        print('  活性  %-10s [%3d..%3d] maxvar=%.4f' % (name, off, off + wd - 1, seg_var))

assert not dead, '恒定段(每段须≥1非常数维): %s' % dead
total_dead = int((V.var(axis=0) < 1e-6).sum())
print('✓ 全部%d段有活性; 整维恒定数=%d/%d (条件性one-hot在合成样本未覆盖属预期)'
      % (len(SEGMENTS), total_dead, fb.CORE_DIMS))
# 定点断言: 本轮修复的死维必须活跃(段10前的偏移不变; 段10后+48)
for idx, why in ((35, '位置带中段(R16修正)'), (36, '位置带高段(R16修正)'),
                 (47, 'dy同高带(R16填[47])'), (283, '密度梯度列0(R16修正)')):
    assert V[:, idx].var() > 1e-6, '维[%d]%s仍恒定' % (idx, why)
# 段11的恒定维必须只在角色one-hot保留位/外部注入位
seg11_const = [i for i in range(227, 253) if V[:, i].var() < 1e-6]
onehot_span = list(range(229, 236)) + list(range(237, 249))
injected = [227, 228, 236]   # train_tm注入opp_id用(本测试不注入, 恒0属预期)
allowed = set(onehot_span) | set(injected)
bad = [i for i in seg11_const if i not in allowed]
assert not bad, '段11非保留位恒定: %s' % bad
print('✓ 定点修复维活跃; 段11恒定维仅剩角色one-hot保留位(%d个)' % len(seg11_const))
print('\n侧向量死区门禁通过 ✓')
