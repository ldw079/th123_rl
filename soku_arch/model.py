# -*- coding: utf-8 -*-
"""模型架构。

本项目提供两个网络，各自的适用条件由【证据】决定，不含未经验证的时序假设：

1. MacroPolicyNet —— 逐拍（无时序）宏策略，**当前唯一可训练**的架构。
   证据：磁盘数据无 match_id/tick_index，game_frame 实为动画帧计数
   （161044 行里回退 69576 次 -> 约 7 万个"边界"、段长中位≈2），
   无法恢复可靠的局/拍结构，因此任何序列建模在此数据上都是无根据的。

2. SequoiaSeqNet（时序，因果 TCN）—— 已实现并单测（形状/ONNX/延迟），
   但在数据契约补齐前 **不可训练**（dataset.split_indices(mode="group") 会明确报错）。
   时序是真正需要的：宏持续时间、对手硬直、威胁接近都需要历史。

共同设计：
  * 残差 MLP 主干（Linear→LayerNorm→GELU）×N，宽度小、常量算力，CPU 友好。
  * 多头：策略头 + 价值头（+ 时序版另有"下一拍宏"自监督辅助头）。
  * 合法性掩码：对非法宏加 -inf（推理与评估使用；掩码来源见 schema.legality_mask）。
  * 所有 op 均为 ONNX 可导出算子（Linear/LayerNorm/GELU/Conv1d/Reshape），
    无动态控制流，固定输入形状。
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn


@dataclass
class ModelConfig:
    n_features: int = 10
    n_macros: int = 55
    hidden: int = 192
    n_blocks: int = 3
    dropout: float = 0.1
    # 时序部分（SequoiaSeqNet）
    seq_len: int = 16
    tcn_blocks: int = 3
    tcn_kernel: int = 3
    use_value_head: bool = True
    use_next_macro_head: bool = False


class ResidualMLPBlock(nn.Module):
    """Pre-LN 残差块：x + dropout(W2(act(W1(LN(x)))))"""

    def __init__(self, hidden: int, dropout: float):
        super().__init__()
        self.norm = nn.LayerNorm(hidden)
        self.fc1 = nn.Linear(hidden, hidden * 2)
        self.act = nn.GELU()
        self.fc2 = nn.Linear(hidden * 2, hidden)
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.norm(x)
        h = self.fc1(h)
        h = self.act(h)
        h = self.fc2(h)
        return x + self.drop(h)


class MacroPolicyNet(nn.Module):
    """逐拍宏策略网络（可训练/可导出，当前数据可用的唯一架构）。"""

    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.inp = nn.Sequential(
            nn.Linear(cfg.n_features, cfg.hidden),
            nn.LayerNorm(cfg.hidden),
            nn.GELU(),
        )
        self.blocks = nn.ModuleList(
            ResidualMLPBlock(cfg.hidden, cfg.dropout) for _ in range(cfg.n_blocks)
        )
        self.norm_out = nn.LayerNorm(cfg.hidden)
        self.policy = nn.Linear(cfg.hidden, cfg.n_macros)
        self.value = nn.Linear(cfg.hidden, 1) if cfg.use_value_head else None

    def forward(
        self, x: torch.Tensor, legal_mask: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor]:
        h = self.inp(x)
        for blk in self.blocks:
            h = blk(h)
        h = self.norm_out(h)
        logits = self.policy(h)
        if legal_mask is not None:
            # 非法宏 -> -inf；用 where 而非 masked_fill 以保持 ONNX 追踪稳定
            neg = torch.full_like(logits, float("-inf"))
            logits = torch.where(legal_mask.to(torch.bool), logits, neg)
        out = {"logits": logits, "hidden": h}
        if self.value is not None:
            out["value"] = torch.tanh(self.value(h)).squeeze(-1)
        return out

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


class CausalDWTCN(nn.Module):
    """因果深度可分离空洞卷积块。

    选择它而不是 GRU 的理由（面向 CPU 单帧预算 16.67ms）：
      * 常量算力、无序列 scan -> ONNX 里是一条 Conv1d，延迟稳定可预测；
      * 感受野 = 1 + 2*(1+2+4+...) 随层数指数增长，K=16 时足以覆盖 ~0.25s 历史；
      * GRU 在 onnxruntime CPU 上需要逐时间步循环，P99 抖动明显更大（TO_VERIFY：
        需在本机实测 GRU vs TCN 的 P99，见 bench.py --compare-gru）。
    """

    def __init__(self, channels: int, kernel: int, dilation: int, dropout: float):
        super().__init__()
        self.dilation = dilation
        self.kernel = kernel
        self.dw = nn.Conv1d(
            channels, channels, kernel,
            padding=dilation * (kernel - 1), groups=channels, dilation=dilation,
        )
        self.norm = nn.LayerNorm(channels)
        self.pw = nn.Conv1d(channels, channels, 1)
        self.act = nn.GELU()
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, T) 因果：裁掉右侧多余 padding
        h = self.dw(x)
        if self.dilation * (self.kernel - 1) > 0:
            h = h[:, :, : x.shape[2]]
        h = h.transpose(1, 2)          # (B, T, C)
        h = self.norm(h)
        h = h.transpose(1, 2)          # (B, C, T)
        h = self.pw(self.act(h))
        return x + self.drop(h)


class SequoiaSeqNet(nn.Module):
    """时序宏策略（因果 TCN + 多头）。数据契约补齐后才可训练。

    输入: (B, T, F) 已标准化特征序列（T = cfg.seq_len，最后一拍为当前拍）
    输出: 当前拍的宏 logits / value / 下一拍宏 logits（自监督辅助）
    """

    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.inp = nn.Sequential(
            nn.Linear(cfg.n_features, cfg.hidden),
            nn.LayerNorm(cfg.hidden),
            nn.GELU(),
        )
        self.tcn = nn.ModuleList(
            CausalDWTCN(cfg.hidden, cfg.tcn_kernel, 2 ** i, cfg.dropout)
            for i in range(cfg.tcn_blocks)
        )
        self.head = ResidualMLPBlock(cfg.hidden, cfg.dropout)
        self.norm_out = nn.LayerNorm(cfg.hidden)
        self.policy = nn.Linear(cfg.hidden, cfg.n_macros)
        self.value = nn.Linear(cfg.hidden, 1) if cfg.use_value_head else None
        self.next_macro = (
            nn.Linear(cfg.hidden, cfg.n_macros) if cfg.use_next_macro_head else None
        )

    def forward(
        self, x: torch.Tensor, legal_mask: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor]:
        # x: (B, T, F)
        h = self.inp(x)                 # (B, T, H)
        h = h.transpose(1, 2)           # (B, H, T)
        for blk in self.tcn:
            h = blk(h)
        h = h.transpose(1, 2)           # (B, T, H)
        h_last = self.norm_out(self.head(h[:, -1, :]))
        logits = self.policy(h_last)
        if legal_mask is not None:
            neg = torch.full_like(logits, float("-inf"))
            logits = torch.where(legal_mask.to(torch.bool), logits, neg)
        out = {"logits": logits, "hidden": h_last}
        if self.value is not None:
            out["value"] = torch.tanh(self.value(h_last)).squeeze(-1)
        if self.next_macro is not None:
            out["next_logits"] = self.next_macro(h_last)
        return out

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


def build_model(name: str, cfg: ModelConfig) -> nn.Module:
    if name == "mlp":
        return MacroPolicyNet(cfg)
    if name == "seq":
        return SequoiaSeqNet(cfg)
    raise ValueError(f"未知模型: {name}")


def receptive_field(cfg: ModelConfig) -> int:
    """因果 TCN 的感受野（拍数）。"""
    return 1 + 2 * sum(2 ** i * (cfg.tcn_kernel - 1) for i in range(cfg.tcn_blocks))


__all__ = [
    "ModelConfig", "ResidualMLPBlock", "MacroPolicyNet", "CausalDWTCN",
    "SequoiaSeqNet", "build_model", "receptive_field",
]
