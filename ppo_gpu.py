# -*- coding: utf-8 -*-
"""R54: PyTorch GPU版PPO — 与ppo.py(numpy CPU)架构逐层对齐、格式兼容。

R53标记的六缺陷全部修复:
1. 维度: CONV 32/64/64+TRUNK 2560(与numpy版/全部现存模型一致)
2. 对手切片: 2*N_OUT + OPP_CORE_OFF(152)
3. save: 直接写numpy键名(W1/W2/W_side/.../W1v/...+meta)
4. load: 显式键映射+转置(非随机形状匹配)
5. 语义: BC+aux+KL自适应+双lr+rstd更新+meta字段序一致
6. minibatch文档与实现一致(64)

等价性验证(R54): 同权重同输入 → P_max_diff=0.000000 V_max_diff=0.000000
(test_gpu_equiv.py)
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
    DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # R14(CPU红线, 用户2026-10-12明令<=75%): torch默认intra-op线程数
    # =全部核心, 3个learner并发即饱和整机 — 限3线程/learner(批耗时
    # 影响轻微); TH123_TORCH_THREADS环境变量可调。
    import os as _os
    torch.set_num_threads(int(_os.environ.get('TH123_TORCH_THREADS', '2')))
except ImportError:
    HAS_TORCH = False
    DEVICE = None

# 与ppo.py共享的架构常量(R54对齐)
CONV_H, CONV_W = 60, 80
CONV1_F, CONV2_F, CONV3_F = 32, 64, 64
TRUNK_FLAT = CONV3_F * 5 * 8         # 2560
HIDDEN = 128
SIDE_H = 64
OPP_DIM = 75
OPP_CORE_OFF = 152
OPP_H1, OPP_H2 = 32, 16
AUX_H = 32
N_OPP_CLS = 8
# S-4阶段2a: GRU形状常量(opp_gru同源)
OPP_GRU_IN = 87
OPP_GRU_H = 24

# numpy版save的键名(必须逐字一致)
_PI_KEYS = ['W1', 'b1', 'W2', 'b2', 'W_side', 'Ws1', 'bs1', 'Ws2', 'bs2',
            'Wo1', 'bo1', 'Wo2', 'bo2', 'W_opp', 'Wq1', 'bq1', 'Wq2', 'bq2',
            'Wc1', 'bc1', 'Wc2', 'bc2', 'Wc3', 'bc3']
_V_KEYS = ['W1v', 'b1v', 'W2v', 'b2v', 'W3v', 'b3v']
# meta字段序(与ppo.py:422一致): temp, beta, bcw, updates, rstd, lr_scale
_META_ORDER = ['_temp', '_beta', '_bcw', '_updates', '_rstd',
               '_adaptive_lr_scale']


if HAS_TORCH:


    class Trunk(nn.Module):
        """卷积主干: 3×60×80 → 2560(与ppo._trunk逐层对应)。"""
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(3, CONV1_F, 3)    # →(B,32,58,78)
            self.conv2 = nn.Conv2d(CONV1_F, CONV2_F, 3)  # →(B,64,27,37)
            self.conv3 = nn.Conv2d(CONV2_F, CONV3_F, 3)  # →(B,64,11,16)

        def forward(self, x):
            a1 = F.relu(self.conv1(x))
            p1 = F.max_pool2d(a1, 2)          # (B,32,29,39)
            a2 = F.relu(self.conv2(p1))       # (B,64,27,37)
            a2 = a2[:, :, :26, :36]           # 裁奇数维(与numpy一致)
            p2 = F.max_pool2d(a2, 2)          # (B,64,13,18)
            a3 = F.relu(self.conv3(p2))       # (B,64,11,16)
            a3 = a3[:, :, :10, :]             # 裁奇数维
            p3 = F.max_pool2d(a3, 2)          # (B,64,5,8)
            return p3.reshape(p3.shape[0], -1)  # (B,2560)


    class PPONet(nn.Module):
        """完整网络: trunk + 策略头 + 侧通路 + 对手子网 + 值头 + 预测头。
        权重名与numpy版逐字一致(直接映射到W1/W2/...键)。"""
        def __init__(self, n_side, n_out):
            super().__init__()
            self.n_side = n_side
            self.n_out = n_out
            self.opp_off = 2 * n_out + OPP_CORE_OFF  # R54: 正确偏移

            self.trunk = Trunk()
            # 策略头 (bias=False: 统一用独立nn.Parameter避免双重偏置)
            self.W1 = nn.Linear(TRUNK_FLAT, HIDDEN, bias=False)
            self.b1 = nn.Parameter(torch.zeros(HIDDEN))
            self.W2 = nn.Linear(HIDDEN, n_out, bias=False)
            self.b2 = nn.Parameter(torch.zeros(n_out))
            # 侧通路
            self.W_side = nn.Linear(n_side, n_out, bias=False)
            self.Ws1 = nn.Linear(n_side, SIDE_H, bias=False)
            self.bs1 = nn.Parameter(torch.zeros(SIDE_H))
            self.Ws2 = nn.Linear(SIDE_H, n_out, bias=False)
            self.bs2 = nn.Parameter(torch.zeros(n_out))
            # 对手子网
            self.Wo1 = nn.Linear(OPP_DIM, OPP_H1, bias=False)
            self.bo1 = nn.Parameter(torch.zeros(OPP_H1))
            self.Wo2 = nn.Linear(OPP_H1, OPP_H2, bias=False)
            self.bo2 = nn.Parameter(torch.zeros(OPP_H2))
            self.W_opp = nn.Linear(OPP_H2, n_out, bias=False)
            # 值头 (输入: trunk + n_side + OPP_H2)
            _vin = TRUNK_FLAT + n_side + OPP_H2
            self.W1v = nn.Linear(_vin, HIDDEN, bias=False)
            self.b1v = nn.Parameter(torch.zeros(HIDDEN))
            self.W2v = nn.Linear(HIDDEN, HIDDEN, bias=False)
            self.b2v = nn.Parameter(torch.zeros(HIDDEN))
            self.W3v = nn.Parameter(torch.zeros(HIDDEN))  # 1-D向量(非矩阵)
            self.b3v = nn.Parameter(torch.zeros(1))
            # 预测头
            _qin = TRUNK_FLAT + OPP_H2
            self.Wq1 = nn.Linear(_qin, AUX_H, bias=False)
            self.bq1 = nn.Parameter(torch.zeros(AUX_H))
            self.Wq2 = nn.Linear(AUX_H, N_OPP_CLS, bias=False)
            self.bq2 = nn.Parameter(torch.zeros(N_OPP_CLS))
            # S-4阶段2a(2026-10-15): GRU表征头 — 参数=OppGRU容器映射
            # (gru_cell冻结: 输入为learner确定性重放的detached repr16;
            # 只训练W_gru; 阶段2b解冻GRU做全BPTT)
            self.gru_cell = nn.GRUCell(OPP_GRU_IN, OPP_GRU_H, bias=True)
            self.gru_W_proj = nn.Linear(OPP_GRU_H, 16, bias=False)
            self.W_gru = nn.Linear(16, n_out, bias=False)
            with torch.no_grad():
                self.W_gru.weight.zero_()   # 零初始化=位等价

            # CE-4(2026-10-15): 一步位置前向头 — trunk+side→隐32→4维
            # (adx'/own_corner'/opp_corner'/air'); MSE辅助损失λ=0.05
            _fin = TRUNK_FLAT + n_side
            self.Wf1 = nn.Linear(_fin, 32, bias=False)
            self.bf1 = nn.Parameter(torch.zeros(32))
            self.Wf2 = nn.Linear(32, 4, bias=False)
            self.bf2 = nn.Parameter(torch.zeros(4))
            with torch.no_grad():
                nn.init.normal_(self.Wf1.weight, std=1.0 / (_fin ** 0.5))
                nn.init.normal_(self.Wf2.weight,
                                std=0.01 / (32 ** 0.5))  # 小初始化

        def forward(self, X, S, temp=1.0, mask=None, gru_reprs=None):
            """X:(B,3,60,80) S:(B,n_side) → logits, value, opp_pred。
            gru_reprs: (B,16) S-4阶段2a — learner按局重放的detached表征。"""
            B = X.shape[0]
            t = self.trunk(X)
            h = F.relu(self.W1(t) + self.b1)
            z = self.W2(h) + self.b2
            z = z + self.W_side(S)
            z = z + self.Ws2(F.relu(self.Ws1(S) + self.bs1)) + self.bs2
            # 对手子网(R54: 正确切片偏移)
            So = S[:, self.opp_off:self.opp_off + OPP_DIM]
            oh = F.relu(self.Wo2(F.relu(self.Wo1(So) + self.bo1))
                        + self.bo2)
            z = z + self.W_opp(oh)
            if gru_reprs is not None:
                # S-4阶段2a: GRU表征→logits(封顶前, 与numpy同位)
                z = z + self.W_gru(gru_reprs)
            # logit封顶(与numpy一致)
            zmax = z.abs().max(dim=1, keepdim=True).values
            z = z / torch.clamp(zmax / 8.0, min=1.0)
            if mask is not None:
                z = z + torch.where(mask, 0.0, -1e9)
            logits = z / temp
            # 值头 (W3v是1-D向量: (B,128)@(128,)→(B,))
            vin = torch.cat([t, S, oh], dim=1)
            h1v = F.relu(self.W1v(vin) + self.b1v)
            h2v = F.relu(self.W2v(h1v) + self.b2v)
            v = h2v @ self.W3v + self.b3v
            # 预测头
            q_in = torch.cat([t, oh], dim=1)
            q = self.Wq2(F.relu(self.Wq1(q_in) + self.bq1)) + self.bq2
            # CE-4: 一步位置前向头(独立计算, 不影响主策略路径)
            fwd_in = torch.cat([t, S], dim=1)
            fwd_h = F.relu(self.Wf1(fwd_in) + self.bf1)
            fwd_pred = self.Wf2(fwd_h) + self.bf2
            return logits, v.squeeze(-1), q, fwd_pred


    class PPOTrainerGPU:
        """GPU版PPO训练器 — API与ppo.PPOTrainer兼容。"""

        # 与numpy版共享的类常量
        GAMMA = 0.999
        LAM = 0.95
        CLIP = 0.2
        EPOCHS = 1
        MINIBATCH = 64
        PI_LR = 3e-4
        VF_LR = 3e-3        # R54: 值头独立lr(原共用3e-4=慢10倍)
        BETA_ENT_0 = 0.02
        BETA_ENT_MIN = 0.001
        ENT_DECAY = 0.97
        BC_W = 0.12
        BC_W_MIN = 0.0
        TARGET_KL = 0.03
        AUX_W = 0.15

        def __init__(self, n_side=None, n_out=None):
            if not HAS_TORCH:
                raise RuntimeError("PyTorch未安装: pip install torch")
            self.n_side = n_side
            self.n_out = n_out
            self.net = PPONet(n_side, n_out).to(DEVICE)
            self.pi_opt = torch.optim.Adam(
                [p for n, p in self.net.named_parameters()
                 if not n.startswith(('W1v', 'b1v', 'W2v', 'b2v',
                                      'W3v', 'b3v'))],
                lr=self.PI_LR)
            self.vf_opt = torch.optim.Adam(
                [p for n, p in self.net.named_parameters()
                 if n.startswith(('W1v', 'b1v', 'W2v', 'b2v',
                                  'W3v', 'b3v'))],
                lr=self.VF_LR)
            self.rng = np.random.default_rng(0)
            self._temp = 2.0
            self._beta = self.BETA_ENT_0
            self._bcw = self.BC_W
            self._updates = 0
            self._rstd = 1.0
            self._adaptive_lr_scale = 1.0
            self._replay_buf = None

        def sample(self, feat, side, temp=None, mask=None, bias=None,
                   return_pred=False):
            """单样本采样(与numpy版接口兼容, 返回宏ID)。
            return_pred=True(S-3, P2从零#4补): 附带(top1宏idx, top1概率)
            — numpy版同契约, 原缺失=GPU路径调用方传参即TypeError(潜伏)。"""
            t = temp if temp is not None else self._temp
            X = torch.from_numpy(
                feat.reshape(1, 3, CONV_H, CONV_W).astype(np.float32)
                / 255.0).to(DEVICE)
            S = torch.from_numpy(
                side.reshape(1, -1).astype(np.float32)).to(DEVICE)
            m = torch.from_numpy(mask.reshape(1, -1)).to(DEVICE) \
                if mask is not None else None
            if bias is not None:
                b = torch.from_numpy(
                    bias.reshape(1, -1).astype(np.float32)).to(DEVICE)
                with torch.no_grad():
                    logits, _, _, _ = self.net(X, S, t, m)
                    # R61f(F3): bias/temp对齐numpy语义(ppo.py:514-516的
                    # softmax((Z+bias)/temp)=Z/temp+bias/temp; 原加在
                    # /temp后差×T系数, 探索强度随温度漂移)
                    logits = logits + b / t
                    probs = F.softmax(logits, dim=1).cpu().numpy()[0]
            else:
                with torch.no_grad():
                    logits, _, _, _ = self.net(X, S, t, m)
                    probs = F.softmax(logits, dim=1).cpu().numpy()[0]
            a = int(self.rng.choice(len(probs), p=probs))
            if return_pred:
                top1 = int(np.argmax(probs))
                return a, (top1, float(probs[top1]))
            return a

        def update(self, feats, acts, rewards, sides, ep_lens,
                   ep_terms=None, ep_first=None, bc_targets=None,
                   bc_mask=None, temp=1.0, masks=None,
                   bc_extra=None, opp_next=None, **kw):
            """批量PPO更新(完整语义: PPO clip + BC + aux + 熵)。
            R61f(F3): 签名对齐numpy版参数序(原第7位是masks而numpy是
            ep_first — 位置调用者会在两个语义间静默错位, 从零审计"签名
            陷阱")。ep_first暂不支持(GPU值头无bootstrap用), 传非None时
            响亮报错。
            stored_logp(kw): R56(fleet红线①) — actor采样时记录的logP(a)
            (N_episode,)float。提供时episode行用它做logp_old(真重要性比,
            与R38回放行同构); 未提供时按现状重算(单实例兼容)。"""
            if ep_first is not None:
                raise NotImplementedError(
                    "ppo_gpu暂不支持ep_first(截断bootstrap) — "
                    "生产路径未使用, 如需启用请先实现值头V(s_end)")
            N = len(acts)
            # 从零#2(等价修复6): 奖励-动作错位结构性断言(numpy版同款)
            assert sum(ep_lens) == N, (
                "ep_lens总和%d != acts长度%d (奖励-动作错位!)"
                % (sum(ep_lens), N))
            # 从零#2(等价修复2): rstd先更后除 — 原先除后更(用旧rstd归一
            # 本批)与numpy语义差一个EMA步, 探针抓出的四个语义差之一
            sd = float(np.asarray(rewards).std())
            if sd > 1e-6:
                self._rstd = 0.8 * self._rstd + 0.2 * sd
            Rn = np.asarray(rewards) / (self._rstd + 1e-6)

            X = torch.from_numpy(
                np.asarray(feats).reshape(-1, 3, CONV_H, CONV_W)
                .astype(np.float32) / 255.0).to(DEVICE)
            S = torch.from_numpy(
                np.asarray(sides).astype(np.float32)).to(DEVICE)
            A = torch.from_numpy(
                np.asarray(acts).astype(np.int64)).to(DEVICE)
            Mt = torch.from_numpy(
                np.asarray(masks).astype(bool)).to(DEVICE) \
                if masks is not None else None

            # R55: 保存CPU副本(回放池用 — 避免GPU→CPU来回)
            X_cpu = np.asarray(feats).astype(np.uint8)
            S_cpu = np.asarray(sides).astype(np.float32)
            A_cpu = np.asarray(acts).astype(np.int64)
            M_cpu = np.asarray(masks).astype(bool) \
                if masks is not None else None
            # S-4阶段2a: 按局重放的detached GRU表征(detach — 只训W_gru)
            gru_reprs = kw.get('gru_reprs')
            G = (torch.from_numpy(np.asarray(gru_reprs, dtype=np.float32))
                 .to(DEVICE) if gru_reprs is not None else None)

            with torch.no_grad():
                logits, V, _, _ = self.net(X, S, temp, Mt, gru_reprs=G)
                logp = F.log_softmax(logits, dim=1)
                # R56(fleet红线①): 采样时记录的logp优先 — ratio=π_new/
                # π_snapshot为真重要性比(陈旧快照经clip正确处理); 无记录
                # 时维持单实例语义(更新时重算, ratio=1近似)
                stored_logp = kw.get('stored_logp')
                if stored_logp is not None:
                    logp_old = np.asarray(
                        stored_logp, dtype=np.float32)
                    assert len(logp_old) == N, (
                        "stored_logp长度%d≠批N%d" % (len(logp_old), N))
                else:
                    logp_old = logp[torch.arange(N), A].cpu().numpy()
                V_np = V.cpu().numpy()

            # GAE
            adv = self._gae(V_np, Rn, ep_lens, ep_terms)
            N0 = N  # 本批episode行数(回放/BC拼接前)
            # R60(F-6): ret必须在归一化**前**算(critic目标=λ回报, numpy版
            # ppo.py:641序) — 原归一化后算 → 值函数学z分数+V, 永不收敛回报
            ret = adv + V_np
            adv = (adv - adv.mean()) / (adv.std() + 1e-6)
            _hi_idx = np.where(np.abs(adv) > 1.0)[0]   # 回放选取(归一化后=1σ)

            # R55(语义对齐): 回放缓冲 — 高优势样本(|adv|>1σ)跨批重用20%
            _replay = getattr(self, '_replay_buf', None)
            _rp_n = 0
            _rows = None
            if _replay is not None and len(_replay[0]) > 0:
                _rp_n = min(len(_replay[0]), max(1, N0 // 5))
                _ridx = self.rng.choice(len(_replay[0]), size=_rp_n,
                                        replace=False)
                _rows = [_replay[k][_ridx] for k in range(8)]
                # 拼接回放行(带保存时logp_old → 真ratio)
                X = torch.cat([X, torch.from_numpy(
                    _rows[0].reshape(-1, 3, CONV_H, CONV_W)
                    .astype(np.float32) / 255.0).to(DEVICE)])
                S = torch.cat([S, torch.from_numpy(
                    _rows[1]).float().to(DEVICE)])
                A = torch.cat([A, torch.from_numpy(
                    _rows[2]).long().to(DEVICE)])
                if G is not None:
                    # S-4: 回放行补零GRU表征(跨批无当前序列上下文)
                    G = torch.cat([G, torch.zeros(
                        _rp_n, 16, device=DEVICE)])
                if Mt is not None:
                    Mt = torch.cat([Mt, torch.from_numpy(
                        _rows[6]).to(DEVICE)])
                adv = np.concatenate([adv, _rows[4]])
                ret = np.concatenate([ret, _rows[5]])
                logp_old = np.concatenate([logp_old, _rows[7]])
                # R60(F-5b): 回放行BC目标=自身动作(numpy版:671同构 —
                # 原GPU不扩展Bt → 拼接后minibatch索引越界)
                if bc_targets is not None:
                    bc_targets = np.concatenate(
                        [np.asarray(bc_targets), _rows[2]])
                # R60(F-5): 回放行无下一拍对手标签 → -1跳过辅助损失
                # (numpy版ppo.py:671有, GPU漏移植 → fleet带opp_next+回放
                # 更新第二次即IndexError)
                if opp_next is not None:
                    opp_next = np.concatenate([
                        np.asarray(opp_next),
                        -np.ones(_rp_n, dtype=np.int64)])
                N = len(A)

            # BC-extra
            if bc_extra is not None:
                Xe, Se, Ye = bc_extra
                Xe_t = torch.from_numpy(
                    np.asarray(Xe).reshape(-1, 3, CONV_H, CONV_W)
                    .astype(np.float32) / 255.0).to(DEVICE)
                Se_t = torch.from_numpy(
                    np.asarray(Se).astype(np.float32)).to(DEVICE)
                Ye_t = torch.from_numpy(
                    np.asarray(Ye).astype(np.int64)).to(DEVICE)
                # R55: expert行ret=各自V(P0-D自洽, 原首行V近似)
                # R60(F-7): expert行logp_old=当前策略logp(numpy版:687) —
                # 原硬0.0 → KL检查|0-logp_new|对低概率专家动作恒读20
                # → 混BC锚时KL虚高0.6+ → 自适应LR永钉0.3×下限
                with torch.no_grad():
                    lo_e, Ve_t, _, _ = self.net(Xe_t, Se_t, temp,
                                             None)
                    logp_e = F.log_softmax(lo_e, dim=1)[
                        torch.arange(len(Ye_t)), Ye_t].cpu().numpy()
                Ve_np = Ve_t.cpu().numpy()
                X = torch.cat([X, Xe_t])
                S = torch.cat([S, Se_t])
                A = torch.cat([A, Ye_t])
                if G is not None:
                    # S-4: BC锚行补零GRU表征(无序列上下文=中性)
                    G = torch.cat([G, torch.zeros(
                        len(Ye_t), 16, device=DEVICE)])
                if Mt is not None:
                    Mt = torch.cat([Mt,
                                    torch.ones(len(Ye_t), self.n_out,
                                               dtype=torch.bool,
                                               device=DEVICE)])
                adv = np.concatenate([
                    adv, np.zeros(len(Ye_t), dtype=np.float32)])
                ret = np.concatenate([ret, Ve_np])
                logp_old = np.concatenate([
                    logp_old, logp_e])
                # R60(F-5b): 专家行BC目标=专家宏(numpy版:701同构)
                if bc_targets is not None:
                    bc_targets = np.concatenate(
                        [np.asarray(bc_targets),
                         np.asarray(Ye, dtype=np.int64)])
                # R60(F-5): 专家行无下一拍标签 → -1
                if opp_next is not None:
                    opp_next = np.concatenate([
                        np.asarray(opp_next),
                        -np.ones(len(Ye_t), dtype=np.int64)])
                N = len(A)

            # R55: bc_mask补齐到总行数(回放行0+专家行1, 与numpy版一致)
            if bc_mask is not None:
                _bm_np = np.asarray(bc_mask, dtype=np.float32)
                _need = N - len(_bm_np)
                if _need > 0:
                    _pad = np.concatenate([
                        np.zeros(min(_rp_n, _need), dtype=np.float32),
                        np.ones(max(0, _need - _rp_n), dtype=np.float32)])
                    if _bm_np.ndim == 2:
                        _pad = _pad[:, None].repeat(_bm_np.shape[1], 1)
                    _bm_np = np.concatenate([_bm_np, _pad])
                bc_mask = _bm_np

            adv_t = torch.from_numpy(adv).float().to(DEVICE)
            ret_t = torch.from_numpy(ret).float().to(DEVICE)
            lp_old_t = torch.from_numpy(
                logp_old).float().to(DEVICE)
            # R56(fleet): bc_targets须转Tensor(原numpy直用 → BC分支
            # cross_entropy收numpy target即TypeError — bcw>0时必炸)
            # 从零#2(等价修复4): None时Bt=None — 原回退A=幽灵自模仿
            # (调用方没给BC目标也吃自模仿梯度, 探针C: b2 25%符号翻转)
            Bt = (torch.from_numpy(np.asarray(bc_targets)).long()
                  .to(DEVICE) if bc_targets is not None else None)

            # 训练循环
            # 从零#2(等价修复1): 归约约定对齐numpy — 策略/熵/BC=sum
            # (numpy的dz逐行无1/B缩放), 值=mean(dv=(V-ret)/B), 辅助=
            # mean-over-valid(AUX_W/nq)。"前向等价≠更新等价"的根因之一。
            losses = []
            v_losses = []
            aux_losses = []
            aux_hits = 0
            aux_n = 0
            kl_val = 0.0
            # S-4守卫: G行数须与批N一致(回放/BC拼接后) — 不等则
            # 降级G=None(W_gru本批不更新), 防IndexError崩训练
            if G is not None and G.shape[0] != N:
                print('[GPU] GRU降级: G=%d行≠批N=%d — 本批W_gru不更新'
                      % (G.shape[0], N))
                G = None
            for _epoch in range(self.EPOCHS):
                perm = self.rng.permutation(N)
                for i0 in range(0, N, self.MINIBATCH):
                    idx = perm[i0:i0 + self.MINIBATCH]
                    idx_t = torch.from_numpy(idx).long().to(DEVICE)
                    xb = X[idx_t]
                    sb = S[idx_t]
                    ab = A[idx_t]
                    bb = Bt[idx_t] if Bt is not None else None
                    mb = Mt[idx_t] if Mt is not None else None
                    advb = adv_t[idx_t]
                    retb = ret_t[idx_t]
                    lpb = lp_old_t[idx_t]

                    logits, V, Q, _fwd = self.net(xb, sb, temp, mb,
                                            gru_reprs=G[idx_t] if G is not None else None)
                    logp_new = F.log_softmax(logits, dim=1)
                    logp_act = logp_new[torch.arange(len(idx)), ab]
                    # P2(审计#3): 对齐numpy侧logp差±20钳制(原缺失=
                    # 降级不对称; 防离群ratio爆炸)
                    ratio = torch.exp(
                        torch.clamp(logp_act - lpb, -20.0, 20.0))
                    surr1 = ratio * advb
                    surr2 = torch.clamp(ratio, 1 - self.CLIP,
                                        1 + self.CLIP) * advb
                    pi_loss = -torch.min(surr1, surr2).sum()
                    v_loss = F.mse_loss(V, retb)
                    ent = -(F.softmax(logits, dim=1)
                            * logp_new).sum(1).sum()

                    # BC损失 (R55: 接入bc_mask逐行权重)
                    # 从零#2(等价修复4): Bt=None不吃BC(幽灵自模仿);
                    # numpy语义=(P-tgt)*bm逐行无均值= sum归约
                    bc_loss = torch.tensor(0.0, device=DEVICE)
                    if self._bcw > 0 and bb is not None:
                        _ce = F.cross_entropy(logits, bb,
                                              reduction='none')
                        if bc_mask is not None:
                            _bm = torch.from_numpy(
                                np.asarray(bc_mask)[idx]
                            ).float().to(DEVICE)
                            if _bm.ndim == 1:
                                _bm = _bm.unsqueeze(1)
                            bc_loss = (_ce.unsqueeze(1) * _bm
                                       ).sum() * self._bcw
                        else:
                            bc_loss = _ce.sum() * self._bcw

                    # aux损失(R54: 预测头监督; mean-over-valid同numpy)
                    aux_loss = torch.tensor(0.0, device=DEVICE)
                    if opp_next is not None:
                        q_t = torch.from_numpy(
                            np.asarray(opp_next)[idx]
                        ).long().to(DEVICE)
                        qv = q_t >= 0
                        if qv.any():
                            aux_loss = F.cross_entropy(
                                Q[qv], q_t[qv]) * self.AUX_W
                            aux_losses.append(
                                float(aux_loss.item() / self.AUX_W))
                            aux_hits += int((Q[qv].argmax(1)
                                             == q_t[qv]).sum())
                            aux_n += int(qv.sum())

                    loss = (pi_loss + 0.5 * v_loss
                            - self._beta * ent + bc_loss + aux_loss)

                    # 从零#2(鲁棒修复1): NaN守卫 — 非有限损失跳批
                    # (原一坏批→内存网永久NaN→僵尸learner)
                    if not torch.isfinite(loss):
                        print('[GPU update] 损失非有限(%s) — 跳过该批'
                              % (float(loss),))
                        self.pi_opt.zero_grad()
                        self.vf_opt.zero_grad()
                        continue
                    self.pi_opt.zero_grad()
                    self.vf_opt.zero_grad()
                    loss.backward()
                    # 从零#2(等价修复3): 裁剪对齐numpy — pi/vf各自独立
                    # 5.0(numpy有效值: 手动10.0+_Adam.GRAD_CLIP=5.0;
                    # 原联合5.0共享预算=值头梯度挤占策略头)
                    _vf_pref = ('W1v', 'b1v', 'W2v', 'b2v', 'W3v', 'b3v')
                    nn.utils.clip_grad_norm_(
                        [p for n, p in self.net.named_parameters()
                         if not n.startswith(_vf_pref)], 5.0)
                    nn.utils.clip_grad_norm_(
                        [p for n, p in self.net.named_parameters()
                         if n.startswith(_vf_pref)], 5.0)
                    self.pi_opt.step()
                    self.vf_opt.step()
                    losses.append(float(pi_loss.item()))
                    v_losses.append(float(v_loss.item()))

            # ---- KL复检+自适应LR(从零#2等价修复5) ----
            # numpy语义(ppo.py:926-946): 每更新一次(非每minibatch),
            # 采样≤500行**同掩码**前向 |Δlogp| 均值; 过阈值缩LR并标停。
            _kidx = self.rng.choice(N, size=min(500, N), replace=False)
            _kt = torch.from_numpy(_kidx).long().to(DEVICE)
            with torch.no_grad():
                _lk, _, _, _ = self.net(X[_kt], S[_kt], temp,
                                     Mt[_kt] if Mt is not None else None)
                _lpk = F.log_softmax(_lk, dim=1)[
                    torch.arange(len(_kidx)), A[_kt]]
                kl_val = float(torch.abs(_lpk - lp_old_t[_kt]).mean())
                # 熵诊断(同掩码 — numpy R18 P0同源)
                _Pk = F.softmax(_lk, dim=1).clamp(1e-8, 1.0)
                ent_diag = float((-(_Pk * _Pk.log()).sum(1)).mean())
            stopped = False
            if kl_val > self.TARGET_KL * 1.5:
                self._adaptive_lr_scale = max(0.3,
                    self._adaptive_lr_scale / 1.5)
            elif kl_val < self.TARGET_KL:
                self._adaptive_lr_scale = min(3.0,
                    self._adaptive_lr_scale * 1.2)
            for g in self.pi_opt.param_groups:
                g['lr'] = self.PI_LR * self._adaptive_lr_scale
            if kl_val > self.TARGET_KL:
                stopped = True

            self._updates += 1
            self._bcw = max(self.BC_W_MIN, self._bcw * self.ENT_DECAY)
            self._beta = max(self.BETA_ENT_MIN,
                             self._beta * self.ENT_DECAY)
            self._temp = max(0.5, self._temp * self.ENT_DECAY)

            # 从零#2(鲁棒修复2): 更新后参数有限性守卫 — 拒绝让NaN网
            # 继续留在内存(learner捕获→隔离批; save守卫是最后防线)
            for _pn, _p in self.net.named_parameters():
                if not torch.isfinite(_p).all():
                    raise ValueError(
                        '更新后参数非有限(%s) — 梯度爆炸/上游数据异常'
                        % _pn)

            # R55: 回放池保存 — 高优势样本(|adv|>1)按|adv|降序取前cap
            # (仅episode行N0内, 防回放行反复入池; 池8元组含mask+logp_old)
            if len(_hi_idx) > 0:
                _cap = min(500, len(_hi_idx))
                _ord = _hi_idx[np.argsort(-np.abs(adv[_hi_idx]))[:_cap]]
                _Mo = M_cpu[_ord] if M_cpu is not None else np.ones(
                    (len(_ord), self.n_out), dtype=bool)
                self._replay_buf = (
                    X_cpu[_ord], S_cpu[_ord], A_cpu[_ord], Rn[_ord],
                    adv[_ord], ret[_ord], _Mo, logp_old[_ord])

            # 从零#2(等价修复7): 统计字典与numpy版逐键对齐(原4键缩水
            # → 仪表/诊断消费方读不到return/kl_stopped/退火值等)
            return {'pi_loss': float(np.mean(losses)) if losses else 0,
                    'return': float(np.mean(ret)),
                    'entropy': ent_diag,
                    'kl': kl_val,
                    'value_loss': (float(np.mean(v_losses))
                                   if v_losses else 0.0),
                    'kl_stopped': stopped,
                    'beta': self._beta, 'temp': self._temp,
                    'bcw': self._bcw,
                    'aux_loss': (float(np.mean(aux_losses))
                                 if aux_losses else None),
                    'aux_acc': (aux_hits / aux_n if aux_n > 0 else None),
                    'adv_abs': float(np.abs(adv).mean()),
                    'kl_abs': abs(kl_val)}

        def _gae(self, V, R, ep_lens, ep_terms):
            N = len(R)
            adv = np.zeros(N, dtype=np.float32)
            start = 0
            for i, L in enumerate(ep_lens):
                end = start + L
                vseg = V[start:end]
                # R56(fleet): ep_terms按**局**索引(非行 — 原ep_terms[start]
                # 单局批(start=0)侥幸正确, 多局批越界; 与numpy版_gae对齐)
                term = bool(ep_terms[i]) \
                    if ep_terms is not None else True
                tail = 0.0 if term else vseg[-1]
                vnext = np.append(vseg[1:], tail)
                delta = R[start:end] + self.GAMMA * vnext - vseg
                acc = 0.0
                for j in range(L - 1, -1, -1):
                    acc = delta[j] + self.GAMMA * self.LAM * acc
                    adv[start + j] = acc
                start = end
            return adv

        def save(self, pi_path, v_path):
            """保存 — numpy格式+NaN守卫(R55)。"""
            # R55: NaN守卫(与numpy版一致 — 检查全部参数)
            for name, p in self.net.named_parameters():
                if not torch.isfinite(p).all():
                    raise ValueError(
                        "save拒绝: %s含NaN/Inf — 查上游特征/梯度" % name)
            sd = self.net.state_dict()

            def _to_np(tname, nname, in_ch=None):
                if tname not in sd:
                    return None
                a = sd[tname].cpu().numpy()
                if in_ch is not None and a.ndim == 4:
                    a = a.reshape(a.shape[0], -1)  # (F,C,3,3)→(F,C*9)
                elif a.ndim == 2 and tname.endswith('.weight') \
                        and '.conv' not in tname:
                    a = a.T  # torch(out,in)→numpy(in,out)
                return nname, a

            # torch参数名→numpy键名 (R54修复: 删重复定义)
            _CONV_MAP = [
                ('trunk.conv1.weight', 'Wc1', 3),
                ('trunk.conv1.bias', 'bc1', None),
                ('trunk.conv2.weight', 'Wc2', CONV1_F),
                ('trunk.conv2.bias', 'bc2', None),
                ('trunk.conv3.weight', 'Wc3', CONV2_F),
                ('trunk.conv3.bias', 'bc3', None),
            ]
            _LIN_MAP = [
                ('W1.weight', 'W1'), ('b1', 'b1'),
                ('W2.weight', 'W2'), ('b2', 'b2'),
                ('W_side.weight', 'W_side'),
                ('Ws1.weight', 'Ws1'), ('bs1', 'bs1'),
                ('Ws2.weight', 'Ws2'), ('bs2', 'bs2'),
                ('Wo1.weight', 'Wo1'), ('bo1', 'bo1'),
                ('Wo2.weight', 'Wo2'), ('bo2', 'bo2'),
                ('W_opp.weight', 'W_opp'),
                ('Wq1.weight', 'Wq1'), ('bq1', 'bq1'),
                ('Wq2.weight', 'Wq2'), ('bq2', 'bq2'),
                ('W1v.weight', 'W1v'), ('b1v', 'b1v'),
                ('W2v.weight', 'W2v'), ('b2v', 'b2v'),
                ('W3v', 'W3v'), ('b3v', 'b3v'),
            ]
            pi_out = {}
            v_out = {}
            # S-4阶段2a: GRU键直卸(GRUCell weight_ih→W_ih等; proj线性
            # torch(out,in)→numpy需转置 — 与_to_np的.T规则不同路径,
            # GRUCell的weight_ih_l0本身就是(3H,IN)=numpy同形, 直拷)
            with torch.no_grad():
                sd_g = self.net.state_dict()
                pi_out['gruW_ih'] = sd_g['gru_cell.weight_ih'].cpu().numpy()
                pi_out['gruW_hh'] = sd_g['gru_cell.weight_hh'].cpu().numpy()
                pi_out['grub_ih'] = sd_g['gru_cell.bias_ih'].cpu().numpy()
                pi_out['grub_hh'] = sd_g['gru_cell.bias_hh'].cpu().numpy()
                pi_out['gruW_proj'] = sd_g['gru_W_proj.weight'].cpu().numpy()  # (16,24)同形直拷
                pi_out['W_gru'] = sd_g['W_gru.weight'].cpu().numpy().T
                # CE-4: 前向头(numpy键; Linear权重torch(out,in)→numpy需.T)
                pi_out['Wf1'] = sd_g['Wf1.weight'].cpu().numpy().T
                pi_out['bf1'] = sd_g['bf1'].cpu().numpy()
                pi_out['Wf2'] = sd_g['Wf2.weight'].cpu().numpy().T
                pi_out['bf2'] = sd_g['bf2'].cpu().numpy()
            _V_KEYS = {'W1v', 'b1v', 'W2v', 'b2v', 'W3v', 'b3v'}
            for tname, nname, in_ch in _CONV_MAP:
                r = _to_np(tname, nname, in_ch)
                if r:
                    pi_out[r[0]] = r[1]
            for tname, nname in _LIN_MAP:
                r = _to_np(tname, nname)
                if r:
                    if r[0] in _V_KEYS:
                        v_out[r[0]] = r[1]    # R54: 值头写v文件
                    else:
                        pi_out[r[0]] = r[1]
            # R61e(F3): 原子落盘(原裸np.savez中断=半档损坏源, 项目惯例
            # tmp+os.replace; npz名须以.npz结尾否则numpy自动补后缀)
            _tp = pi_path + '.tmp.npz'
            np.savez(_tp, **pi_out,
                     meta=np.array([
                         self._temp, self._beta, self._bcw,
                         float(self._updates), self._rstd,
                         self._adaptive_lr_scale],
                         dtype=np.float32))
            os.replace(_tp, pi_path)
            # R54修复: 值头参数写v文件(原全写pi文件+v文件只写dummy
            # → numpy版load从v文件读W1v时ValueError=GPU→numpy方向断)
            _tv = v_path + '.tmp.npz'
            np.savez(_tv, **v_out)
            os.replace(_tv, v_path)

        def load(self, pi_path, v_path):
            """加载 — 显式键映射+转置; 值头从v_path读(R54修复)。"""
            d_pi = np.load(pi_path)
            d_v = np.load(v_path) if os.path.exists(v_path) else {}
            # 合并: 值头参数在v文件中(numpy版save分开存)
            merged = {k: d_pi[k] for k in d_pi.files}
            for k in getattr(d_v, 'files', []):
                if k != 'dummy' and k not in merged:
                    merged[k] = d_v[k]
            sd = {}

            def _from_np(nname, tname, in_ch=None):
                if nname not in merged:
                    return None
                a = merged[nname]
                if in_ch is not None and a.ndim == 2:
                    a = a.reshape(a.shape[0], in_ch, 3, 3)
                elif a.ndim == 2 and tname.endswith('.weight') \
                        and '.conv' not in tname:
                    a = a.T  # numpy(in,out)→torch(out,in)
                param = dict(self.net.named_parameters()).get(tname)
                if param is not None and param.shape == a.shape:
                    return tname, torch.from_numpy(a)
                if param is not None:
                    # P0-A(从零#2共犯): 形状不符原只打印继续 → 随机权重
                    # 无声混入被发布(fleet静默零学习的链条一环)。
                    # 修: 响亮拒载(learner/supervisor接管重启, 好于腐坏发布)
                    raise ValueError(
                        '[GPU load] 形状不符: %s 文件%s≠网络%s — 拒绝加载'
                        ' (维度推断过期或档损坏)' % (
                            nname, a.shape, tuple(param.shape)))
                return None

            _CONV_MAP = [
                ('Wc1', 'trunk.conv1.weight', 3),
                ('bc1', 'trunk.conv1.bias', None),
                ('Wc2', 'trunk.conv2.weight', CONV1_F),
                ('bc2', 'trunk.conv2.bias', None),
                ('Wc3', 'trunk.conv3.weight', CONV2_F),
                ('bc3', 'trunk.conv3.bias', None),
            ]
            _LIN_MAP = [
                ('W1', 'W1.weight'), ('b1', 'b1'),
                ('W2', 'W2.weight'), ('b2', 'b2'),
                ('W_side', 'W_side.weight'),
                ('Ws1', 'Ws1.weight'), ('bs1', 'bs1'),
                ('Ws2', 'Ws2.weight'), ('bs2', 'bs2'),
                ('Wo1', 'Wo1.weight'), ('bo1', 'bo1'),
                ('Wo2', 'Wo2.weight'), ('bo2', 'bo2'),
                ('W_opp', 'W_opp.weight'),
                ('Wq1', 'Wq1.weight'), ('bq1', 'bq1'),
                ('Wq2', 'Wq2.weight'), ('bq2', 'bq2'),
                ('W1v', 'W1v.weight'), ('b1v', 'b1v'),
                ('W2v', 'W2v.weight'), ('b2v', 'b2v'),
                ('W3v', 'W3v'), ('b3v', 'b3v'),
            ]
            # S-4阶段2a: GRU键(numpy→torch; 旧档缺键=位等价起步)
            # S-4阶段2a: GRU参数无条件入sd(strict要求全覆盖) —
            # 缺省=构造初值(W_gru零=位等价), 有键则覆盖
            with torch.no_grad():
                _cur = dict(self.net.named_parameters())
                sd['gru_cell.weight_ih'] = _cur['gru_cell.weight_ih'].data.clone()
                sd['gru_cell.weight_hh'] = _cur['gru_cell.weight_hh'].data.clone()
                sd['gru_cell.bias_ih'] = _cur['gru_cell.bias_ih'].data.clone()
                sd['gru_cell.bias_hh'] = _cur['gru_cell.bias_hh'].data.clone()
                sd['gru_W_proj.weight'] = _cur['gru_W_proj.weight'].data.clone()
                sd['W_gru.weight'] = _cur['W_gru.weight'].data.clone()
                sd['Wf1.weight'] = _cur['Wf1.weight'].data.clone()
                sd['bf1'] = _cur['bf1'].data.clone()
                sd['Wf2.weight'] = _cur['Wf2.weight'].data.clone()
                sd['bf2'] = _cur['bf2'].data.clone()
            if 'gruW_ih' in merged:
                sd['gru_cell.weight_ih'] = torch.from_numpy(merged['gruW_ih'])
                sd['gru_cell.weight_hh'] = torch.from_numpy(merged['gruW_hh'])
                sd['gru_cell.bias_ih'] = torch.from_numpy(merged['grub_ih'])
                sd['gru_cell.bias_hh'] = torch.from_numpy(merged['grub_hh'])
                sd['gru_W_proj.weight'] = torch.from_numpy(
                    merged['gruW_proj'])   # (16,24)同形
                sd['W_gru.weight'] = torch.from_numpy(merged['W_gru'].T)
                if 'Wf1' in merged:
                    sd['Wf1.weight'] = torch.from_numpy(merged['Wf1'].T)
                    sd['bf1'] = torch.from_numpy(merged['bf1'])
                    sd['Wf2.weight'] = torch.from_numpy(merged['Wf2'].T)
                    sd['bf2'] = torch.from_numpy(merged['bf2'])
            # R63(P1-5): 可选参数(旧代际档合法缺失 — 与numpy版load同哲学:
            # 侧非线性头Ws1/Ws2与对手子网络Wo1/Wo2/W_opp/Wq1/Wq2在早期档
            # 中不存在, 缺失时保持"零输出起步"的init值, 不算腐坏)。
            _OPTIONAL = ('Ws1', 'bs1', 'Ws2', 'bs2', 'Wo1', 'bo1', 'Wo2',
                         'bo2', 'W_opp', 'Wq1', 'bq1', 'Wq2', 'bq2')
            _missing = []
            for nname, tname, in_ch in _CONV_MAP:
                r = _from_np(nname, tname, in_ch)
                if r:
                    sd[r[0]] = r[1]
                elif nname not in _OPTIONAL:
                    _missing.append(nname)
            for item in _LIN_MAP:
                nname, tname = item
                r = _from_np(nname, tname, None)
                if r:
                    sd[r[0]] = r[1]
                elif nname not in _OPTIONAL:
                    _missing.append(nname)
            # R63(P1-5): 缺失参数**响亮拒载** — 原 strict=False 只打印
            # "[GPU load] 缺失键" 后继续, 于是"缺value档"或"旧格式缺
            # 对手子网络"会**静默保留随机初始化的critic**, 而该critic
            # 立即被publish_snapshot发布成fleet快照, 并驱动 train_tm 的
            # 价值引导宏重选(30%决策) → 随机critic直接污染行为数据;
            # GAE目标同样出自随机V(numpy版同场景是raise, GPU版是打印,
            # 双实现不对称)。
            if _missing:
                raise ValueError(
                    '[GPU load] 参数缺失%d项: %s — 拒绝加载(缺失=随机初始化'
                    '混入被发布; 检查pi/v档配对与代际)' % (
                        len(_missing), _missing[:8]))
            result = self.net.load_state_dict(sd, strict=False)
            if result.missing_keys:
                # 已声明required全齐 → 这里只可能是映射表未覆盖的新参数
                raise ValueError(
                    '[GPU load] 仍有未映射参数: %s — 映射表过期, 拒绝加载'
                    % (result.missing_keys[:8],))
            if 'meta' in merged:
                m = merged['meta']
                self._temp = float(m[0])
                self._beta = float(m[1])
                self._bcw = float(m[2])
                self._updates = int(m[3])
                self._rstd = float(m[4])
                # R61f(F3): 旧档meta仅5元素(无lr_scale) → 越界IndexError
                # (镜像ppo.py:309-311的len守卫, 缺省1.0)
                self._adaptive_lr_scale = (float(m[5])
                                           if len(m) >= 6 else 1.0)

else:
    class PPOTrainerGPU:
        def __init__(self, *a, **kw):
            raise RuntimeError(
                "PyTorch未安装 — pip install torch")
