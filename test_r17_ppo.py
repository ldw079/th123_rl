# -*- coding: utf-8 -*-
"""R17对手建模四件套冒烟: ③子网络前向影响 + ④辅助梯度有限差分校验 + 回环。
④方法: 捕集一次update传给_pi_adam的梯度表, 对Wq1/Wq2(纯辅助路参数)
做中心差分 — 符号或接线错误会直接表现为符号翻转。"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from macros import N_MACROS
from ppo import PPOTrainer

N_SIDE = 2 * N_MACROS + 308
OPP_OFF = 2 * N_MACROS + 152
rng = np.random.default_rng(7)

N = 64
X = rng.integers(0, 255, size=(N, 14400)).astype(np.uint8)
S = (rng.random((N, N_SIDE)) * 0.2).astype(np.float32)
y = rng.integers(0, 8, size=N)
S[np.arange(N), OPP_OFF + y] = 0.9
acts = rng.integers(0, N_MACROS, size=N)
rews = rng.normal(0, 0.3, size=N).astype(np.float32)
ep_lens = [N // 2, N - N // 2]
opp_next = y.copy()
opp_next[-1] = -1
M = np.ones((N, N_MACROS), dtype=bool)

t = PPOTrainer(n_side=N_SIDE, n_out=N_MACROS)
t.init_fresh(N_SIDE)

# ③ 子网络影响检查: W_opp非零后, 采样分布必须随对手切片变化
P0 = t._pi_forward(X[:8].astype(np.float32), S[:8])[2]
t.W_opp[:] = rng.standard_normal(t.W_opp.shape).astype(np.float32) * 0.3
S2 = S[:8].copy()
S2[:, OPP_OFF:OPP_OFF + 8] = np.eye(8, dtype=np.float32)[:8] * 0.9
P1 = t._pi_forward(X[:8].astype(np.float32), S[:8])[2]
P2 = t._pi_forward(X[:8].astype(np.float32), S2)[2]
assert np.abs(P1 - P0).max() > 1e-6, "W_opp非零但输出无变化(子网络未接线)"
assert np.abs(P2 - P1).max() > 1e-6, "对手切片变化不影响策略(子网络失明)"
t.W_opp[:] = 0.0
print("✓ ③对手子网络已接线: 策略分布随对手切片变化")


# ④ 辅助梯度有限差分: 复现update内的辅助前向(同一公式)
def aux_loss(tr, Xb, Sb, yb):
    """float64计算: Wq1链路梯度小, float32下FD的ΔL被舍入噪声淹没。"""
    Xn = tr._trunk_fwd_chunked(Xb.astype(np.float32)).astype(np.float64)
    _, Oh = tr._opp_fwd(Sb)
    q_in = np.concatenate([Xn, Oh.astype(np.float64)], axis=1)
    Hq = np.maximum(0, q_in @ tr.Wq1.astype(np.float64) + tr.bq1)
    zq = Hq @ tr.Wq2.astype(np.float64) + tr.bq2
    zq = zq - zq.max(1, keepdims=True)
    e = np.exp(zq)
    Pq = e / e.sum(1, keepdims=True)
    return float(-np.log(np.clip(Pq[np.arange(len(yb)), yb],
                                 1e-12, 1.0)).mean())


cap = {}
_orig_step = t._pi_adam.step


def _cap_step(grads, lr, maximize=False):
    cap['pg'] = [g.copy() for g in grads]


# FD严格同样本集: 单minibatch全批(N=64=MINIBATCH)+全有效标签 →
# 捕获槽与真梯度有关系 _pg[Wq*] = -s·AUX_W·(dL/dWq*)(s=裁剪10/_pn>0;
# dq的AUX_W/nq缩放被全批均值FD恰好消去)
_lab = y.copy()
t._pi_adam.step = _cap_step
st = t.update(list(X), acts, rews, list(S), ep_lens, masks=M,
              opp_next=_lab, temp=1.0)
t._pi_adam.step = _orig_step
assert 'pg' in cap, "update未触达_pi_adam(梯度被吞?)"
print("  update stats: aux_loss=%.4f aux_acc=%.1f%% vl=%.3f"
      % (st["aux_loss"], st["aux_acc"] * 100, st["value_loss"]))

# 槽位: [W1(0) b1(1) W2(2) b2(3) W_side(4) Ws1(5) bs1(6) Ws2(7) bs2(8)
#        Wo1(9) bo1(10) Wo2(11) bo2(12) W_opp(13) Wq1(14) bq1(15)
#        Wq2(16) bq2(17) Wc1(18) ...] — _pg里辅助头已取负(下降→上升约定)
SLOT = {"Wq1": 14, "Wq2": 16}
EPS = 1e-3
rs_all = []
for name, slot, _tries, _need in (("Wq2", 16, 12, 4), ("Wq1", 14, 24, 3)):
    P = getattr(t, name)
    g_slot = cap['pg'][slot]
    rs = []
    for _ in range(_tries):
        if len(rs) >= _need:
            break
        i = int(rng.integers(0, P.shape[0]))
        j = int(rng.integers(0, P.shape[1]))
        sv = P[i, j]
        P[i, j] = sv + EPS
        lp = aux_loss(t, X, S, _lab)
        P[i, j] = sv - EPS
        lm = aux_loss(t, X, S, _lab)
        P[i, j] = sv
        fd = (lp - lm) / (2 * EPS)   # dL/dP 数值(全批均值)
        if abs(fd) > 1e-6:           # 死ReLU行自动跳过
            rs.append(-g_slot[i, j] / (t.AUX_W * fd))
    assert len(rs) >= _need, "%s FD有效点不足" % name
    assert all(r > 0 for r in rs), \
        "%s比值r须全正(符号反/接线断): %s" % (name, ['%.3f' % r for r in rs])
    med = float(np.median(rs))
    dev = max(abs(r - med) for r in rs) / (med + 1e-12)
    assert dev < 0.35, \
        "%s比值不一致(接线半通): med=%.4f dev=%.0f%%" % (name, med, dev * 100)
    rs_all.append(med)
    print("  %s: 裁剪缩放s≈%.3f, 比值偏差<%.0f%%" % (name, med, dev * 100))
print("✓ ④动作预测辅助梯度与有限差分严格一致(符号/缩放/接线)")

# 学习方向软校验: 同批连续update, aux_loss不得上升
hist = [st["aux_loss"]]
for _ in range(3):
    st = t.update(list(X), acts, rews, list(S), ep_lens, masks=M,
                  opp_next=opp_next, temp=1.0)
    hist.append(st["aux_loss"])
    assert np.isfinite(st["value_loss"]) and st["aux_loss"] is not None
assert hist[-1] <= hist[0] + 1e-3, "连续update后aux_loss上升: %s" % hist
print("✓ 连续update辅助损失不升: %.4f→%.4f" % (hist[0], hist[-1]))

# 保存/加载回环: 参数逐位一致 + 同输入同分布
tmp = tempfile.mkdtemp()
pp, vp = os.path.join(tmp, "pi.npz"), os.path.join(tmp, "v.npz")
t.save(pp, vp)
t2 = PPOTrainer(n_side=N_SIDE, n_out=N_MACROS)
t2.load(pp, vp)
for k in ("W_side", "Ws1", "Ws2", "Wo1", "Wo2", "W_opp", "Wq1", "Wq2",
          "W1v", "W1"):
    assert np.array_equal(getattr(t, k), getattr(t2, k)), "保存/加载不一致: " + k
Pa = t._pi_forward(X[:4].astype(np.float32), S[:4])[2]
Pb = t2._pi_forward(X[:4].astype(np.float32), S[:4])[2]
assert np.abs(Pa - Pb).max() < 1e-7, "加载后前向不一致"
_, Va, _ = t._v_forward(t._trunk(X[:4].astype(np.float32))[0], S[:4])
_, Vb, _ = t2._v_forward(t2._trunk(X[:4].astype(np.float32))[0], S[:4])
assert np.abs(Va - Vb).max() < 1e-5, "加载后值头不一致"
print("✓ 保存/加载回环: 参量逐位一致, 策略/价值前向一致")
print("\nR17 PPO冒烟通过 ✓ (n_side=%d n_out=%d)" % (N_SIDE, N_MACROS))
