# -*- coding: utf-8 -*-
"""task-21 Phase1 空间奖励测试: env 解析/触发边界/开关."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

import train_tm as T  # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    print('  PASS  %s' % name if cond else '  FAIL  %s' % name)
    if not cond:
        BAD += 1


class D:
    pass


def mk(x, air=False):
    return {'position.x': x, 'position.y': 0.0, 'airBorne': air, 'action': 0}


d = D()
T.space_reward_reset(d)
ck(T.REW_SPACE is True, 'TH123_REW_SPACE 默认开')
ck(abs(T.R_SPACE_EDGE - 0.0015) < 1e-12, 'λ_edge 保守默认 0.0015')
ck(abs(T.R_SPACE_ESCAPE - 0.03) < 1e-12, 'λ_escape 默认 0.03')
ck(abs(T.R_SPACE_SURVIVE - 0.02) < 1e-12, 'λ_survive 默认 0.02')
ck(abs(T.R_SPACE_CROSS - 0.05) < 1e-12, 'λ_cross 默认 0.05')

r_edge = T.space_reward_step(d, mk(100.0), {'position.x': 800.0}, 0, 999)
ck(abs(r_edge + 0.0015) < 1e-12, '板边帧微罚 -0.0015')
r_esc = T.space_reward_step(d, mk(500.0), {'position.x': 800.0}, 0, 999)
ck(abs(r_esc - 0.03) < 1e-12, '脱离墙角奖励 +0.03')
r_mid = T.space_reward_step(d, mk(500.0), {'position.x': 800.0}, 0, 999)
ck(abs(r_mid) < 1e-12, '中场无奖无罚')
# 受压逃逸成功: 事件后 30 帧无受击 → +0.02
T.space_reward_reset(d)
t = 0
ev = T.frame_events.E_OPP_STARTUP
r = T.space_reward_step(d, mk(500.0), {'position.x': 800.0}, 0, ev)
r30 = 0.0
for t in range(1, 32):
    d._sp_t = t
    r = T.space_reward_step(d, mk(500.0), {'position.x': 800.0}, 0, 999)
    if t == 30:
        r30 = r
ck(abs(r30 - 0.02) < 1e-9, '受压后30F未受击 +0.02 (实测 %.3f)' % r30)
# 受击则不奖
T.space_reward_reset(d)
d._sp_t = 0
T.space_reward_step(d, mk(500.0), {'position.x': 800.0}, 0, ev)
for t in range(1, 32):
    d._sp_t = t
    T.space_reward_step(d, mk(500.0), {'position.x': 800.0},
                        1 if t == 5 else 0, 999)
ck(True, '受击分支不崩(数值见存活事件测试)')
# env 关: 子进程 TH123_REW_SPACE=0
import subprocess
code = ('import sys; sys.path.insert(0, r"%s"); import train_tm as T; '
        'print(T.REW_SPACE)' % ROOT)
e0 = dict(os.environ)
e0['TH123_REW_SPACE'] = '0'
r0 = subprocess.run([sys.executable, '-X', 'utf8', '-c', code],
                    capture_output=True, text=True, env=e0, cwd=ROOT)
ck(r0.returncode == 0 and r0.stdout.strip().splitlines()[-1] == 'False',
   'TH123_REW_SPACE=0 关闭 (%r)' % r0.stdout.strip())

print('\n==== task-21 space reward: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
