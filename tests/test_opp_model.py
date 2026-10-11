# -*- coding: utf-8 -*-
"""P0-L行为测试(第十六轮审查§2): 9情境全可达 + 6段占据无恒零/无混叠。
对照缺陷: 旧ctx_id只产出{0,1,3,4,6,7}, 旧bands用cur_ctx%6折叠
(bands[2]/bands[5]恒零, bands[0]/bands[1]接收两个情境的混叠贡献)。
R17(2026-10-01): 增历史/资源条件化行为测试; features 27→75维。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # 相对路径: 变异沙箱内解析到沙箱树
from opp_model import (OpponentModel, STAGE_W, A_ATTACK, A_IDLE,
                        A_GUARD, A_BULLET, GUARD_ALL_IDS)
# ↑ test_threat.py同款: pyenv嵌入式python不自动加脚本目录, 见其文件头

GUARD_IDS = GUARD_ALL_IDS   # R21: XML权威防御集150-167(旧{110-115}为受击/倒地)
HIST_OFF, RES_OFF = 27, 27 + 40   # features内偏移: 基础27|历史40|资源8


def _feed(m, dx, opp_x, act=A_IDLE, n=20):
    for _ in range(n):
        m.update(1.0 / 62, False, act, dx, 0.0, 1000, None, None,
                 opp_x, GUARD_IDS, False, False)


# 测试1: 9情境全部可达
m = OpponentModel()
seen = set()
for d, dx in ((0, 80), (1, 300), (2, 700)):
    for z, x in ((0, 60), (1, 600), (2, 1200)):
        mm = OpponentModel()
        _feed(mm, dx, x)
        seen.add(mm.cur_ctx)
assert seen == set(range(9)), '9情境应全可达, 实际%s' % sorted(seen)
print('✓ 9情境全部可达:', sorted(seen))

# 测试2: 6段占据无恒零 — 各喂一段, 每段都应收到独立贡献
m = OpponentModel()
for band in range(6):
    x = (band + 0.5) * STAGE_W / 6   # 段中心
    _feed(m, 300, x, n=62)
f = m.features()
bands = f[8:14]
assert all(v > 0.01 for v in bands), '6段占据应全非零, 实际%s' % (bands,)
print('✓ 6段占据全非零:', ['%.2f' % v for v in bands])

# 测试3: 无混叠 — 只喂段k时, 其余段应≈0(排除EMA残留)
m = OpponentModel()
_feed(m, 300, 0.5 * STAGE_W / 6, n=62)   # 只在段0
f = m.features()
bands = f[8:14]
assert bands[0] > 0.5 and all(v < 0.01 for v in bands[1:]), \
    '单段驻留不应泄漏到其他段, 实际%s' % (bands,)
print('✓ 无混叠: 仅段0驻留 →', ['%.3f' % v for v in bands])

# 测试4: 情境行读取正确 — 近距+攻动作 → 情境0行攻桶占比高
# R28: act=300(5A, SokuLib枚举; 旧250系冲刺区非攻击)
m = OpponentModel()
_feed(m, 80, 60, act=300, n=62)          # 近距+左段+攻击ID
f = m.features()
assert f[1] > 0.9, '情境0(近距×左段)攻击占比应≈1, 实际%.2f' % f[1]
print('✓ 情境行按(距离×位置)路由: 攻桶=%.2f' % f[1])

# 测试5: features恒75维且无NaN(R17: 基础27+历史40+资源8)
m = OpponentModel()
_feed(m, 300, 600)
f = m.features()
assert len(f) == 75 and all(v == v and abs(v) != float('inf') for v in f), \
    '75维有限数, 实际len=%d' % len(f)
print('✓ features 75维有限')

# 测试6: ctx_id边界 — x恰在段界/超界不崩
for dx, x in ((-5, -10), (2000, 1300), (0, 413.333), (130, 826.666)):
    OpponentModel.ctx_id(dx, x)
print('✓ ctx_id边界(负x/超界/段界)不崩')

# 测试7(R17①): 动作历史 — 序列[怠,怠,防,攻,攻]后, 历史栈逐位按 A_* 点亮。
# R21: 动作ID用XML权威值(150=立防; 旧用112/820 — 112实为倒地, 820无效)
m = OpponentModel()
m.update(1.0 / 62, False, 4, 300, 0.0, 1000, None, None, 600,
         GUARD_IDS, False, False)          # 怠
m.update(1.0 / 62, False, 4, 300, 0.0, 1000, None, None, 600,
         GUARD_IDS, False, False)          # 怠
m.update(1.0 / 62, False, 150, 300, 0.0, 1000, None, None, 600,
         GUARD_IDS, False, False)          # 防(立防150, XML权威)
m.update(1.0 / 62, False, 300, 300, 0.0, 1000, None, None, 600,
         GUARD_IDS, False, False)          # 攻(5A, R28枚举语义)
m.update(1.0 / 62, False, 320, 300, 0.0, 1000, None, None, 600,
         GUARD_IDS, False, False)          # 攻(5AA, R28枚举语义)
f = m.features()
seq = [A_IDLE, A_IDLE, A_GUARD, A_ATTACK, A_ATTACK]   # 旧→新
for step, cls in enumerate(seq):
    blk = f[HIST_OFF + step * 8: HIST_OFF + step * 8 + 8]
    on = [i for i, v in enumerate(blk) if v > 0.5]
    assert on == [cls], '历史步%d应点亮类%d, 实际%s' % (step, cls, on)
print('✓ 动作历史滚动正确: 旧→新=%s' % seq)

# 测试8(R17②): 资源条件化 — 灵满时攻/灵空时守, 两分布应分别点亮
m = OpponentModel()
for _ in range(62):    # 灵力1000(>=500)持续攻击(5A, R28枚举)
    m.update(1.0 / 62, False, 300, 300, 0.0, 1000, None, None, 600,
             GUARD_IDS, False, False)
for _ in range(62):    # 灵力200(<500)持续防御(立防150, R21)
    m.update(1.0 / 62, False, 150, 300, 0.0, 200, None, None, 600,
             GUARD_IDS, False, False)
f = m.features()
full4 = f[RES_OFF:RES_OFF + 4]        # [防,攻,射,机]
low4 = f[RES_OFF + 4:RES_OFF + 8]
assert full4[1] > 0.9, '灵满时攻占比应≈1, 实际%s' % (full4,)
assert low4[0] > 0.9, '灵空时防占比应≈1, 实际%s' % (low4,)
print('✓ 资源条件化: 灵满[防攻射机]=%s 灵空=%s'
      % (['%.2f' % v for v in full4], ['%.2f' % v for v in low4]))

print('\n全部P0-L行为测试通过 ✓')
