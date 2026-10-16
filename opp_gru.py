# -*- coding: utf-8 -*-
"""S-4(合并终版方案第二波): 对手+自我序列记忆 GRU — 预备件(未接线).

设计(系列方案§5 + 合并方案S-4, 2026-10-14):
- 输入87维 = side对手切片75 [2N+152:2N+227] + S-2段12 [2N+330:2N+342]
  (4 punish+2 pred+4 反重复+2 风格pc — **全部在side向量内 → 可从
  存储sides逐拍重放**, 循环组件进PPO的唯一无歧义路径; K5位342不入
  — 静态身份不进序列记忆)
- 隐状态24维(合并方案: 16→24)
- 对手表征 = [既有16维MLP输出 ‖ h_t投影16] = 32维(值/策略/aux三处)
- BPTT: 场内截断起步(跨场只传值不传梯度; 3场窗口待阶段0消融后扩)
- 系列内跨场h携带: SeriesManager管控(E1b启用后)
- 双梯度源: RL对局 + BC专家序列(S-6序列采样接入后)

本模块只含cell与前向/重放工具 — ppo/ppo_gpu接线在S-4批次本体
(重启归因窗口之后), 当前无人import = flag-off。
"""
from __future__ import annotations

import numpy as np

OPP_GRU_IN = 87      # 75对手切片 + 12 S-2段
OPP_GRU_H = 24
OPP_SLICE_OFF = 152  # side[2N+152:2N+227] = opp_model 75维
S2_SEG_OFF = 330     # side[2N+330:2N+342] = S-2段12维(不含K5的342)


def gru_cell(x, h_prev, W_ih, W_hh, b_ih, b_hh):
    """手写GRUCell(P2-3共享源契约, 2026-10-14晚审计):

    **规范源=torch.nn.GRUCell公式**(r=sigmoid(W_ir x+b_ir+W_ir h+b_ir),
    z=…, n=tanh(W_in x+b_in+r*(W_hn h+b_hn)), h'=(1-z)n+z h);
    本函数是其numpy实现(actor侧无torch依赖); 二者不允许第三种写法。
    **等价由test_opp_gru_s4钉死(1.5e-07), 且该测试已入C15行为门禁** —
    任何一侧公式漂移=门禁红(2026-10-14前该测试未注册白名单, 漂移
    无闸, 已修)。改公式必须两侧同改+等价测试同步。

    x: (IN,) h_prev: (H,) W_ih: (3H, IN) W_hh: (3H, H) b: (3H,)
    """
    H = h_prev.shape[0]
    gi = x @ W_ih.T + b_ih
    gh = h_prev @ W_hh.T + b_hh
    i_r, i_z, i_n = gi[0:H], gi[H:2 * H], gi[2 * H:]
    h_r, h_z, h_n = gh[0:H], gh[H:2 * H], gh[2 * H:]
    r = 1.0 / (1.0 + np.exp(-(i_r + h_r)))
    z = 1.0 / (1.0 + np.exp(-(i_z + h_z)))
    n = np.tanh(i_n + r * h_n)
    return (1.0 - z) * n + z * h_prev


def gru_slice(side, n_macros):
    """side向量 → 87维GRU输入(静态函数, 在线/重放同一路径)."""
    b = 2 * n_macros
    return np.concatenate([side[b + OPP_SLICE_OFF:b + OPP_SLICE_OFF + 75],
                           side[b + S2_SEG_OFF:b + S2_SEG_OFF + 12]])


class OppGRU:
    """GRU参数容器+序列前向(numpy版; GPU版S-4批次在ppo_gpu对齐)。

    h语义: 系列内跨场传值(不传梯度), 系列边界reset;
    h=None=新系列。update()逐决策拍; replay()整序列确定性重放。
    """

    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        s = 1.0 / np.sqrt(OPP_GRU_IN)
        self.W_ih = (rng.standard_normal((3 * OPP_GRU_H, OPP_GRU_IN))
                     * s).astype(np.float32)
        self.b_ih = np.zeros(3 * OPP_GRU_H, dtype=np.float32)
        s2 = 1.0 / np.sqrt(OPP_GRU_H)
        self.W_hh = (rng.standard_normal((3 * OPP_GRU_H, OPP_GRU_H))
                     * s2).astype(np.float32)
        self.b_hh = np.zeros(3 * OPP_GRU_H, dtype=np.float32)
        # h_t投影16维(对手表征拼接用)
        self.W_proj = (rng.standard_normal((16, OPP_GRU_H))
                       * s2).astype(np.float32)

    def step(self, x87, h_prev):
        if h_prev is None:
            h_prev = np.zeros(OPP_GRU_H, dtype=np.float32)
        return gru_cell(np.asarray(x87, dtype=np.float32), h_prev,
                        self.W_ih, self.W_hh, self.b_ih, self.b_hh)

    def replay(self, sides_seq, n_macros, h0=None):
        """整序列重放(离线learner路径 — 与在线逐步step逐位一致)."""
        h = h0
        hs = []
        for side in sides_seq:
            h = self.step(gru_slice(side, n_macros), h)
            hs.append(h)
        return hs

    def repr16(self, h):
        """对手表征的GRU分量(16维投影, 与MLP16拼接成32)."""
        return np.tanh(self.W_proj @ h)
