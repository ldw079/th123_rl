# -*- coding: utf-8 -*-
"""R17(§3.8): _drain的EOF行为测试(配对变异性质):
对端FIN后recv返回b''不抛异常 — 若回归为"丢弃返回值的紧循环",
本测试将死循环 → 子进程超时 → 门禁红。D1曾说已修, R17审计发现回归。"""
import socket
import sys
import time
import types

sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # 相对路径: 变异沙箱内解析到沙箱树
from tm_env import TMEnv

a, b = socket.socketpair()
# 对端: 发一批残留数据然后关闭(FIN)
b.sendall(b'x' * 200000)
b.close()

# 构造最小env桩: _drain只触碰self.inst.sock
env = object.__new__(TMEnv)
env.inst = types.SimpleNamespace(sock=a)

t0 = time.time()
TMEnv._drain(env)   # 若FIN死循环回归 → 此处永不返回 → 超时红
dt = time.time() - t0
assert dt < 2.0, '_drain耗时%.1fs(应<2s)' % dt
# 排干后再读应是EOF(不抛BlockingIOError即已死循环的形态, 防御性断言)
a.setblocking(False)
try:
    rest = a.recv(65536)
except (BlockingIOError, ConnectionResetError):
    rest = b'ok'
assert rest in (b'', b'ok'), '排干不彻底: %r' % rest[:20]
a.close()
print('✓ _drain遇FIN正常返回(%.2fs), 排空干净' % dt)
print('\n_drain EOF行为测试通过 ✓')
