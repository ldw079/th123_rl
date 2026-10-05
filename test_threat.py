# -*- coding: utf-8 -*-
"""threat_predict 行为测试: 零速弹必须被排除。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # 相对路径: 变异沙箱内解析到沙箱树
from threat import threat_predict

# 测试1: 全零速弹表 → (None, 0)
r = threat_predict(500, 100, [(-1, 500, 100, 0.0, 0.0)])
assert r == (None, 0), '全零速弹应返回(None,0), 实际%s' % (r,)
print('✓ 零速弹贴脸 → (None, 0)')

# 测试2: 零速弹+运动弹 → 只算运动弹的TTI
r = threat_predict(500, 100, [(-1, 500, 100, 0.0, 0.0), (1, 800, 100, -10.0, 0.0)])
assert r[1] == 1, '来袭数应只算1(运动弹), 实际%d' % r[1]
assert r[0] is not None and r[0] > 0, 'TTI应>0, 实际%s' % (r[0],)
print('✓ 零速+运动弹 → TTI=%.1f incoming=%d' % r)

# 测试3: 仅运动弹 (800→500, vx=-10, HITBOX_X=70 → t0=23帧)
r = threat_predict(500, 100, [(1, 800, 100, -10.0, 0.0)])
assert r == (23.0, 1), '运动弹TTI应=23帧, 实际%s' % (r,)
print('✓ 仅运动弹 → TTI=%.1f incoming=%d' % r)

# 测试4: 空弹表
r = threat_predict(500, 100, [])
assert r == (None, 0)
print('✓ 空弹表 → (None, 0)')

print('\n全部行为测试通过 ✓')
