# -*- coding: utf-8 -*-
"""R17对手子网络+预测辅助的快速行为测试(C15门禁版; 完整深测见
test_r17_ppo.py — 本件砍FD点数/批量保秒级, 供变异自检反复运行)。
1) 子网络接线: W_opp非零后策略分布随对手切片变化;
2) 辅助梯度: 捕集_pi_adam梯度, Wq2与有限差分一致(符号/接线);
3) 保存/加载: 新参数(Wo*/W_opp/Wq*)逐位往返。"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from ppo import PPOTrainer

N_OUT = 6
N_SIDE = 2 * N_OUT + 308
OPP_OFF = 2 * N_OUT + 152
# _pi_adam槽位: [...W_opp(13) Wq1(14) bq1(15) Wq2(16)...]
rng = np.random.default_rng(11)

N = 64
X = rng.integers(0, 255, size=(N, 14400)).astype(np.uint8)
S = (rng.random((N, N_SIDE)) * 0.2).astype(np.float32)
y = rng.integers(0, 8, size=N)
S[np.arange(N), OPP_OFF + y] = 0.9
acts = rng.integers(0, N_OUT, size=N)
rews = rng.normal(0, 0.3, size=N).astype(np.float32)
M = np.ones((N, N_OUT), dtype=bool)

t = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
t.init_fresh(N_SIDE)

# 1) 子网络接线
P0 = t._pi_forward(X[:8].astype(np.float32), S[:8])[2]
t.W_opp[:] = rng.standard_normal(t.W_opp.shape).astype(np.float32) * 0.3
P1 = t._pi_forward(X[:8].astype(np.float32), S[:8])[2]
S2 = S[:8].copy()
S2[:, OPP_OFF:OPP_OFF + 8] = np.eye(8, dtype=np.float32) * 0.9
P2 = t._pi_forward(X[:8].astype(np.float32), S2)[2]
assert np.abs(P1 - P0).max() > 1e-6, 'W_opp非零但输出不变(子网络未接线)'
assert np.abs(P2 - P1).max() > 1e-6, '对手切片变化不影响策略(子网络失明)'
t.W_opp[:] = 0.0
print('✓ 对手子网络接线: 策略分布随对手切片变化')


def aux_loss(tr, Xb, Sb, yb):
    Xn = tr._trunk_fwd_chunked(Xb.astype(np.float32))
    _, Oh = tr._opp_fwd(Sb)
    Hq = np.maximum(0, np.concatenate([Xn, Oh], 1) @ tr.Wq1 + tr.bq1)
    zq = Hq @ tr.Wq2 + tr.bq2
    zq = zq - zq.max(1, keepdims=True)
    e = np.exp(zq)
    Pq = e / e.sum(1, keepdims=True)
    return float(-np.log(np.clip(Pq[np.arange(len(yb)), yb], 1e-8, 1.0)).mean())


# 2) 辅助梯度FD校验。捕获槽与真梯度有严格关系:
#    _pg[Wq*] = -s·AUX_W·(dL/dWq*)   (s>0常数=范数裁剪10/_pn, 未裁则1;
#    dq按AUX_W/nq缩放, 全批均值FD恰消去nq) → 比值 r=-pg/(AUX_W·fd)
#    必须为**正**且跨entries**一致**。符号变异→r<0红; 接线断裂→r乱红。
cap = {}
lab = y.copy()   # 全有效(N=MINIBATCH单批, fd与捕获严格同样本集)
t._pi_adam.step = lambda g, l, maximize=False: cap.__setitem__(
    'pg', [x.copy() for x in g])
t.update(list(X), acts, rews, list(S), [N], masks=M,
         opp_next=lab.astype(np.int64), temp=1.0)
g_wq2, g_wq1 = cap['pg'][16], cap['pg'][14]
EPS = 1e-3


def _fd_points(P, g_slot, tries, need):
    """随机采样FD点; 死ReLU行fd=0自动跳过(带重试)。"""
    rs = []
    for _ in range(tries):
        if len(rs) >= need:
            break
        i = int(rng.integers(0, P.shape[0]))
        j = int(rng.integers(0, P.shape[1]))
        sv = P[i, j]
        P[i, j] = sv + EPS
        lp = aux_loss(t, X, S, lab)
        P[i, j] = sv - EPS
        lm = aux_loss(t, X, S, lab)
        P[i, j] = sv
        fd = (lp - lm) / (2 * EPS)
        if abs(fd) > 1e-6:
            rs.append(-g_slot[i, j] / (t.AUX_W * fd))
    return rs


rs = _fd_points(t.Wq2, g_wq2, tries=12, need=4) \
    + _fd_points(t.Wq1, g_wq1, tries=14, need=2)
assert len(rs) >= 4, 'FD有效点不足(死单元过多), 扩点数'
assert all(r > 0 for r in rs), '比值r须全正(符号反/接线断): %s' % ['%.3f' % r for r in rs]
med = float(np.median(rs))
dev = max(abs(r - med) for r in rs) / (med + 1e-12)
assert dev < 0.35, '比值不一致(接线半通): med=%.4f dev=%.0f%%' % (med, dev * 100)
print('✓ 预测辅助梯度FD一致: 裁剪缩放s=%.3f, 8点比值偏差<%.0f%%'
      % (med, dev * 100))

# 3) 保存/加载回环(新参数逐位)
tmp = tempfile.mkdtemp()
pp, vp = os.path.join(tmp, 'pi.npz'), os.path.join(tmp, 'v.npz')
t.save(pp, vp)
t2 = PPOTrainer(n_side=N_SIDE, n_out=N_OUT)
t2.load(pp, vp)
for k in ("Wo1", "bo1", "Wo2", "bo2", "W_opp", "Wq1", "bq1", "Wq2", "bq2"):
    assert np.array_equal(getattr(t, k), getattr(t2, k)), '往返不一致: ' + k
assert np.array_equal(t._opp_fwd(S[:4])[1], t2._opp_fwd(S[:4])[1])
print('✓ 新参数保存/加载逐位一致')
print('\n对手子网络+预测辅助行为测试通过 ✓')
