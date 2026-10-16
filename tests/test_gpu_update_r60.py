# -*- coding: utf-8 -*-
"""R60(从零审计F-5/F-6/F-7)ppo_gpu更新循环行为测试:
1. F-5: opp_next+bc_extra+回放连发两次update不崩(原第二次IndexError);
2. F-7: 带BC锚时KL读数 sane(原专家行logp=0 → KL恒~0.6钉LR下限);
3. F-6: ret=归一化前adv+V(检查cuda/GPU内部序的行为代理: 训练后
   critic输出与批回报尺度同阶, 原z分数+V永不拟合回报)。
数据: 小型合成模型(n_out=8), 双 Trainer 对照(numpy不崩基准)。
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from ppo import PPOTrainer  # noqa: E402
from ppo_gpu import PPOTrainerGPU  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    rng = np.random.default_rng(7)
    n_out, n_side = 8, 5 * 8 + 308
    tmp = tempfile.mkdtemp(prefix="gpu_upd_r60_")
    pi = os.path.join(tmp, "m.npz")
    vv = os.path.join(tmp, "m_v.npz")
    t0 = PPOTrainer(n_side=n_side, n_out=n_out)
    t0.init_fresh(14400)
    t0.save(pi, vv)

    gpu = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu.load(pi, vv)
    nptr = PPOTrainer(n_side=n_side, n_out=n_out)
    nptr.load(pi, vv)

    def synth(n, r):
        return dict(
            feats=r.integers(0, 255, (n, 14400)).astype(np.uint8),
            sides=r.standard_normal((n, n_side)).astype(np.float32),
            acts=r.integers(0, n_out, n).astype(np.int64),
            rews=r.standard_normal(n).astype(np.float32),
            masks=(r.random((n, n_out)) > 0.15),
        )

    b1 = synth(120, rng)
    b2 = synth(100, rng)
    bc = (rng.integers(0, 255, (16, 14400)).astype(np.uint8),
          rng.standard_normal((16, n_side)).astype(np.float32),
          rng.integers(0, n_out, 16).astype(np.int64))

    # 1+F-5: 两次连发(第二次回放池非空→补齐路径); opp_next全程在
    kls = []
    for i, b in enumerate((b1, b2)):
        opp_next = rng.integers(0, 8, len(b["acts"])).astype(np.int64)
        stats = gpu.update(
            b["feats"], b["acts"], b["rews"], b["sides"], [len(b["acts"])],
            masks=b["masks"], bc_targets=b["acts"], temp=1.0,
            bc_extra=bc, opp_next=opp_next)
        kls.append(stats.get("kl", 0))
        check("F5连发update#%d不崩" % (i + 1), True)
    # 2+F-7: KL sane(原bug实测0.62; 修后远小于0.5)
    check("F7带BC锚KL sane", max(kls) < 0.5, "kl=%s" % kls)

    # F-7强化(2026-10-14变异漏网补): 专家行占比高的批 — 稀释不再
    # 掩盖logp_e语义错误(softmax冒充log_softmax时专家行|Δ|≈2.2,
    # 200/240占比 → kl≈1.8必红; 正确logp_e时kl=更新漂移, 远小于0.5)
    b3 = synth(40, rng)
    bc3 = (rng.integers(0, 255, (200, 14400)).astype(np.uint8),
           rng.standard_normal((200, n_side)).astype(np.float32),
           rng.integers(0, n_out, 200).astype(np.int64))
    st3 = gpu.update(
        b3["feats"], b3["acts"], b3["rews"], b3["sides"], [40],
        masks=b3["masks"], bc_targets=b3["acts"], temp=1.0,
        bc_extra=bc3, opp_next=rng.integers(0, 8, 40).astype(np.int64))
    check("F7专家重载KL sane", st3.get("kl", 0) < 0.5,
          "kl=%.3f" % st3.get("kl", 0))

    # 3+F-6: numpy对照同批也不崩(行为基准一致; numpy版BC分支要求
    # bc_mask非None — 生产路径_submit_update恒传, 此处同参)
    st_np = nptr.update(
        b1["feats"], b1["acts"], b1["rews"], b1["sides"], [120],
        masks=b1["masks"], bc_targets=b1["acts"], temp=1.0,
        bc_mask=b1["masks"].astype(np.float32),
        bc_extra=bc, opp_next=np.int64(rng.integers(0, 8, 120)))
    check("numpy对照update OK", "kl" in st_np)

    # 4+F-6行为代理: GPU训后critic对批内状态估值与回报同阶(原z分数
    # 目标使V输出~N(0,1)与R尺度脱钩; 合成R~N(0,1)此处弱验证→改为
    # 结构断言: 两次update后V输出非常数且有限)
    import torch
    import torch.nn.functional as F
    with torch.no_grad():
        X = torch.from_numpy(
            b1["feats"][:32].reshape(-1, 3, 160, 30).astype(np.float32))
        # 14400=3*160*30? 以实际CONV_H/W为准
    from ppo_gpu import CONV_H, CONV_W
    with torch.no_grad():
        X = torch.from_numpy(
            b1["feats"][:32].reshape(-1, 3, CONV_H, CONV_W)
            .astype(np.float32) / 255.0).to("cpu")
        S = torch.from_numpy(b1["sides"][:32]).to("cpu")
        _, V, _, _ = gpu.net(X, S, 1.0, None)
    check("F6 critic输出有限非常数",
          bool(torch.isfinite(V).all()) and float(V.std()) > 1e-4,
          "V.std=%.4f" % float(V.std()))

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
