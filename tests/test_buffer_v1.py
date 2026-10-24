# -*- coding: utf-8 -*-
"""task-29/30 阶段1: 缓冲原语 C15(BufferState 纯逻辑 + gate stun 白名单 + env=0)."""
import importlib
import os
import sys

import numpy as np

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
os.chdir(WT)
FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


print('== buffer v1 ==')
os.environ['TH123_BUFFER'] = '1'
import buffer_primitives as B  # noqa: E402
importlib.reload(B)
NAMES = ['待机', '跳跃', '5A', 'jA', '立防', '受身', '236B']
st = B.BufferState(NAMES)
chk('allowed 只含 buf 槽(跳跃/5A)', st.allowed == {1, 2})
chk('stun 帧登记', st.register(1, True) and st.active and st.pending[0] == 1)
chk('重复登记覆盖旧 pending', st.register(2, True) and st.dropped == 1
    and st.pending[0] == 2)
chk('stun 中 resolve 不执行', st.resolve(True) is None)
chk('解硬直首帧执行', st.resolve(False)[0] == 2 and not st.active)
chk('非 buf 槽不登记', st.register(4, True) is False)
chk('非 stun 不登记', st.register(1, False) is False)
# max_wait 过期丢弃
st3 = B.BufferState(NAMES)
chk('dir 令牌登记/传递',
    st3.register(1, True, direction='forward')
    and st3.resolve(False)[1] == 'forward')
st2 = B.BufferState(NAMES, max_wait=2)
st2.register(1, True)
for _ in range(3):
    st2.resolve(True)
chk('超过 max_wait 丢弃', not st2.active and st2.dropped == 1)
st.note_outcome(True)
st.note_outcome(False)
chk('执行结果 acted 统计', 'acted=1/2' in st.stats_line())
chk('dir 计数(dir_f/dir_b/dir_n)',
    st.dir_n >= 1 and st.dir_f == 0
    and 'dir_f=' in st.stats_line())
chk('stats_line 格式', '[buffer] registered=' in st.stats_line())

# P1-2: 方向受身接线(extra_allowed) / drop 拆分 / rehit8
st4 = B.BufferState(NAMES + ['受身'], extra_allowed=('受身',))
chk('受身 extra_allowed 可登记且带方向',
    st4.register(NAMES.__len__(), True, direction='back')
    and st4.dir_b == 1)
st4.register(NAMES.__len__(), True, direction='forward')
chk('覆盖计数 drop_ow', st4.drop_ow == 1 and st4.drop_to == 0)
st4.resolve(False)
chk('drop 分类独立', st4.drop_to == 0)
st5 = B.BufferState(NAMES, max_wait=2)
st5.register(1, True)
for _ in range(3):
    st5.resolve(True)
chk('超时计数 drop_to', st5.drop_to == 1 and st5.drop_ow == 0)
st5.note_outcome(True, True)
chk('rehit8 埋点', 'rehit8=1/1' in st5.stats_line()
    and 'drop_to=' in st5.stats_line())
# task-56: ONCE(每硬直段仅1次登记) / NO_OVERWRITE(pending 不覆盖)
st6 = B.BufferState(NAMES, once=True)
st6.update_stun(True)
chk('ONCE 首登记成功', st6.register(1, True))
chk('ONCE 段内屏蔽', st6.mask_blocked()
    and not st6.register(1, True) and st6.once_block == 1)
st6.update_stun(True)
chk('ONCE 同段仍屏蔽', st6.mask_blocked())
st6.update_stun(False)
st6.update_stun(True)
chk('ONCE 新段可再登记', st6.register(1, True) and st6.seg_id == 2)
st7 = B.BufferState(NAMES, no_overwrite=True)
_a = st7.register(1, True)
_b = st7.register(1, True)
chk('NO_OVERWRITE 覆盖返回False且计数不变', _a and not _b
    and st7.registered == 1 and st7.drop_ow == 0 and st7.ow_block == 1)
st7.update_stun(True)
chk('NO_OVERWRITE pending 时 mask 屏蔽', st7.mask_blocked())
st7.resolve(False)
chk('NO_OVERWRITE pending 清空后可登记', st7.register(1, True))
# gate: stun 帧白名单并集/env=0 旧行为
import game_gates as G  # noqa: E402
importlib.reload(G)
N8 = ['待机', '跳跃', '5A', 'jA', '立防', '受身', '236B', '空防']
mg = G.apply_state_gates(np.ones(8, bool), N8,
                         {'action': 60, 'airBorne': False})
chk('受创帧放 受身+跳跃+5A(不含待机/攻击/防御)',
    bool(mg[1]) and bool(mg[2]) and bool(mg[5])
    and not mg[0] and not mg[3] and not mg[4] and not mg[6])
# task-32: 防御取消白名单(env 开/关)
os.environ['TH123_GUARD_CANCEL'] = '1'
importlib.reload(G)
mgc = G.apply_state_gates(np.ones(8, bool), N8,
                          {'action': 151, 'airBorne': False})
chk('防御取消白名单 env=1 放开近战(5A/2A)',
    bool(mgc[1]) and bool(mgc[2]))
os.environ['TH123_GUARD_CANCEL'] = '0'
importlib.reload(G)
os.environ['TH123_BUFFER'] = '0'
importlib.reload(G)
mg0 = G.apply_state_gates(np.ones(8, bool), N8,
                          {'action': 60, 'airBorne': False})
chk('env=0 受创帧仅受身(buf 关闭)',
    bool(mg0[5]) and not mg0[0] and not mg0[1] and not mg0[2])
os.environ['TH123_BUFFER'] = '1'
importlib.reload(G)
line = G.startup_line()
chk('startup_line 含 buffer=1/K', 'buffer=1' in line and 'K=' in line)

# train_tm 接线源码级
tt = open(os.path.join(WT, 'train_tm.py'), encoding='utf8').read()
chk('train_tm 接线 BufferState/register/resolve',
    'BufferState(' in tt and 'self._buf_state.register(' in tt
    and 'self._buf_state.resolve(' in tt and 'stats_line()' in tt)
print('==== buffer v1: %d PASS / %d FAIL ====' % (29 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
