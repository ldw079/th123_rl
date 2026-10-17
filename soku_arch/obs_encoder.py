# -*- coding: utf-8 -*-
"""观测编码器：把**全面观测**压成 K 个"软前缀" token 送进 SokuLM。

为什么必须这样（本次实测得出的硬约束）：
  实测 T=128 时 2M 参数已达 P95 94.8ms、30M 参数 434ms（见 docs/RESULTS.md §5）。
  也就是说 **token 数是与参数量同量级的成本项**。若把 ~200 维观测各占一个 token，
  T 立刻上到 200+，延迟必然崩 —— 于是"信息更全"和"跑得动"直接冲突。

解法：观测**不进 token 序列**，而是经 MLP 压成 K 个 d_model 维连续向量（软前缀），
拼在 token 嵌入前面。于是：
  * 输入信息量：~200 维标量 + K_b 个弹幕对象（旧 11 维的 18 倍以上）
  * 序列长度：仅增加 K（默认 8）
  * 推理成本：多一次 200×256 的矩阵乘（~0.05 MFLOP），可忽略

弹幕单独用**置换不变的集合编码器**（per-object MLP + masked max/mean 池化），
取代旧 6×6 网格量化 —— 网格把"哪颗弹、朝哪、多快"糊成了占用计数。
"""
from __future__ import annotations

import torch
import torch.nn as nn


class BulletSetEncoder(nn.Module):
    """变长弹幕集合 → 定长向量（置换不变）。

    * per-object MLP 提取单弹语义（相对位置/速度/朝向/招式号）
    * masked max + masked mean 双池化：max 保留"最危险的弹"，mean 保留整体密度
    * 空集合安全：mask 全 0 时用 where 归零，不产生 NaN/inf
    """

    def __init__(self, in_dim: int, hidden: int = 64, out_dim: int = 128, dropout: float = 0.0):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
        )
        self.proj = nn.Linear(hidden * 2, out_dim)
        self.drop = nn.Dropout(dropout)

    def forward(self, bullets: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """bullets: (B, K, D)；mask: (B, K) float 0/1。返回 (B, out_dim)。"""
        h = self.mlp(bullets)                          # (B, K, H)
        m = mask.unsqueeze(-1)                         # (B, K, 1)
        denom = m.sum(dim=1)                           # (B, 1)
        hmean = (h * m).sum(dim=1) / denom.clamp(min=1.0)
        # 用大负数替代 -inf，保证 ONNX 数值稳定；全空时再用 where 归零
        hmax = (h - 1e4 * (1.0 - m)).max(dim=1).values
        hmax = torch.where(denom > 0, hmax, torch.zeros_like(hmax))
        return self.drop(self.proj(torch.cat([hmax, hmean], dim=-1)))


class ObservationEncoder(nn.Module):
    """(dense, bullets, mask) → (B, n_soft, d_model) 软前缀。

    结构：dense MLP ⊕ bullet set encoder → fuse MLP → Linear(n_soft × d_model) → reshape。
    最后一层一次性生成全部软 token（比拼 K 个独立头更省、更稳）。
    """

    def __init__(
        self, dense_dim: int, bullet_dim: int, d_model: int, n_soft: int = 8,
        hidden: int = 256, bullet_hidden: int = 64, bullet_out: int = 128,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.dense_dim = dense_dim
        self.n_soft = n_soft
        self.d_model = d_model
        self.bullet_enc = BulletSetEncoder(bullet_dim, bullet_hidden, bullet_out, dropout)
        self.dense_mlp = nn.Sequential(
            nn.Linear(dense_dim, hidden), nn.LayerNorm(hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
        )
        self.fuse = nn.Sequential(
            nn.Linear(hidden + bullet_out, hidden), nn.LayerNorm(hidden), nn.GELU(),
        )
        self.to_soft = nn.Linear(hidden, n_soft * d_model)
        self.norm_out = nn.LayerNorm(d_model)
        self.drop = nn.Dropout(dropout)

    def forward(self, dense: torch.Tensor, bullets: torch.Tensor,
                mask: torch.Tensor, return_feat: bool = False):
        """返回软前缀 (B, n_soft, d_model)；return_feat=True 时同时返回融合特征 (B, hidden)。

        融合特征供"直接宏头"使用（见 ObsConditionedLM(direct_head=True)）：
        它是一条比"软前缀→注意力→在 <act> 位读数"更短的梯度路径。
        """
        b = self.bullet_enc(bullets, mask)
        d = self.dense_mlp(dense)
        h = self.fuse(torch.cat([d, b], dim=-1))
        soft = self.to_soft(h).view(-1, self.n_soft, self.d_model)
        soft = self.drop(self.norm_out(soft))
        return (soft, h) if return_feat else soft

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


class ObsConditionedLM(nn.Module):
    """SokuLM + 观测编码器 的端到端封装（导出与部署的唯一入口）。

    输入: input_ids (B, T_tok)、dense (B, F)、bullets (B, K, D)、mask (B, K)
    输出: logits (B, K_soft + T_tok, V)
    宏 token 的下标 = n_soft + action_pos。

    direct_head=True 时额外提供一条"观测 → 宏"的直接读数路径（返回 `summarize` 的结构见
    `forward_aux`）。**动机（有实测依据）**：受控实验里同一信息下，软前缀路径需要
    约 5–10× 优化步数才能追上直接线性读数（docs/RESULTS.md §11.4）。直接头是一条
    更短的梯度路径，作为多任务辅助信号；LM 路径保持不变，生成能力不受影响。

    `prev_residual=True` 时再加一条**残差通路**：把"上一拍输入"的 one-hot 直接加到
    宏 logits 上（系数 1.0）。**动机同样是实测的**：`prev_off` 消融把 top1 从 0.8879
    打到 0.3558，说明"上一拍输入"是信息主体；但主臂 **0.8879 < 零参数门槛 0.8882**，
    即模型**连"照抄上一拍"这个恒等映射都没学出来**（本批训练 loss 仍有 3.95≈随机）。
    残差让"照抄"成为**架构默认行为**，模型只需学**增量**（何时该改），
    而不是从零重建恒等映射。

    实现上要求 `dense` 的**末块**是 prev 块（`bc_frame --prev-input joint` 的布局：
    第 0 列有效位 + 144 列 one-hot），并需要 `prev_valid_dim=145`。
    """

    def __init__(self, lm: nn.Module, obs: ObservationEncoder, n_macros: int | None = None,
                 direct_head: bool = False, prev_residual: bool = False,
                 prev_block_dim: int = 0, learnable_residual_scale: bool = False):
        super().__init__()
        self.lm = lm
        self.obs = obs
        hidden = obs.fuse[0].out_features
        self.direct = nn.Linear(hidden, int(n_macros)) if direct_head else None
        self.n_macros = int(n_macros) if n_macros is not None else 0
        self.prev_residual = bool(prev_residual)
        self.prev_block_dim = int(prev_block_dim)
        self.learnable_residual_scale = bool(learnable_residual_scale)
        # 可学残差强度：sigmoid(raw)∈(0,1)，raw=3 ⇒ 初始 ≈0.953（≈固定 1.0 的旧行为）
        self.residual_scale_raw = (nn.Parameter(torch.tensor(3.0))
                                   if (self.prev_residual and self.learnable_residual_scale)
                                   else None)
        if self.prev_residual:
            if self.prev_block_dim <= 0:
                raise ValueError("prev_residual=True 需要 prev_block_dim>0（prev 块维度）")
            if self.n_macros <= 0:
                raise ValueError("prev_residual=True 需要 n_macros>0")

    def residual_scale(self) -> torch.Tensor:
        """当前残差强度（标量）。

        **为什么需要"可学"**：固定 1.0 等价于一个**硬编码的决策阈值** ——
        它规定"模型额外 logit 要超过 1.0 才能改写照抄结果"。而实测（12 分片／8 epoch）
        表明**该改的行是少数**：探针分数最高的 2% 行里只有 32.8% 真该变。
        也就是说最优阈值依赖数据，写死必然次优（残差臂 −0.0003 就是它的代价）。
        让 sigmoid(raw) 可学，optimizer 自己找这个阈值。
        """
        if self.residual_scale_raw is None:
            return torch.tensor(1.0)
        return torch.sigmoid(self.residual_scale_raw)

    def zero_init_head(self) -> int:
        """把 LM 的 `lm_head` 权重**零初始化**，返回被清零的元素数。

        为什么：`prev_residual=True` 的设计意图是"**照抄上一拍**是架构默认行为，
        模型只学增量"。但 `SokuLM` 用 GPT-2 式初始化（`std=0.02`），head 输入经 RMSNorm
        后≈单位尺度、输出 255 类求和 ⇒ 初始宏 logits 的 std ≈ 0.02×√d_model ≈ 0.23，
        与残差的 1.0 同量级 ⇒ **起点不是精确的"照抄"**，模型还得先学会压制这个噪声。

        清零后：**训练第一步就精确等于 persistence 基线**，此后只学"何时该改"。
        （`tie_embeddings=True` 时 head 与 `tok_emb` 共享权重 —— 那种情况下**不清**，
        因为会同时毁掉词嵌入；本函数的返回值让人能看出有没有真的清。）

        实测结论见 docs/RESULTS.md §15：单独加残差已有 +0.0059，清零再叠一层。
        """
        head = getattr(self.lm, "lm_head", None)
        if head is None or getattr(head, "weight", None) is None:
            return 0
        tok = getattr(self.lm, "tok_emb", None)
        if tok is not None and head.weight is tok.weight:
            return 0                      # 权重共享：清 head 等于清 embedding，不能做
        with torch.no_grad():
            head.weight.zero_()
        return int(head.weight.numel())

    def _prev_onehot(self, dense: torch.Tensor) -> torch.Tensor:
        """从 dense 末块取上一拍 one-hot：列 0 = 有效位，列 1..n_macros = one-hot。

        返回值已乘上**残差强度**（固定 1.0 或可学的 sigmoid(raw)），
        因此训练与评测两条路径自动一致（调用方只做 `logits + prev_onehot`）。
        """
        tail = dense[:, -self.prev_block_dim:]
        valid = tail[:, :1]                      # (B,1) 1=已知 0=未知
        onehot = tail[:, 1:1 + self.n_macros] * valid
        if self.residual_scale_raw is not None:
            onehot = onehot * self.residual_scale().to(onehot.dtype)
        return onehot

    def forward(self, input_ids: torch.Tensor, dense: torch.Tensor,
                bullets: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """仅 LM 路径（保持 ONNX 导出契约稳定）。"""
        soft = self.obs(dense, bullets, mask)
        logits, _ = self.lm(input_ids, soft_prefix=soft)
        return logits

    def forward_aux(self, input_ids: torch.Tensor, dense: torch.Tensor,
                    bullets: torch.Tensor, mask: torch.Tensor) -> dict:
        """训练用：同时给出 LM 路径与直接头（若启用）+ 上一拍残差（若启用）。"""
        soft, feat = self.obs(dense, bullets, mask, return_feat=True)
        logits, _ = self.lm(input_ids, soft_prefix=soft)
        out = {"logits": logits, "feat": feat}
        if self.prev_residual:
            out["prev_onehot"] = self._prev_onehot(dense)
        if self.direct is not None:
            out["direct"] = self.direct(feat)
        return out

    def macro_position(self, action_pos: int) -> int:
        return self.obs.n_soft + action_pos

    def n_params(self) -> int:
        seen, total = set(), 0
        for p in self.parameters():
            if id(p) not in seen:
                seen.add(id(p))
                total += p.numel()
        return total


__all__ = ["BulletSetEncoder", "ObservationEncoder", "ObsConditionedLM"]
