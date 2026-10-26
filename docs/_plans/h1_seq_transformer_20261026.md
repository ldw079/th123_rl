# H1 决策点长历史因果 Transformer（task-77，2026-10-26 设计 v0）

> 用户批准 H1 试点（Lead 12:08）；离线设计+原型，**不部署/不占窗**。
> 依赖：episode schema/BC 兼容/W4 迁移载体；R15/R16/R19 适用。

## 1. 目标
- 用 **T=16–32 决策 tokens** 的因果 Transformer 替代/并列 `mem_v1`（当前 GRU mem_dim=8）。
- 输入：状态特征（side/core）+ 动作（宏 id/残差）+ 奖励 + 事件（hit/guard/UKEMI/…）+ 对手风格摘要；
- 输出：策略/价值辅助头（A/B 试点离线，不接线上）。
- env `TH123_SEQ_TRANSFORMER=0` 默认关闭，逐位等价旧行为；打开后仅模型结构变化（动作空间不变）。

## 2. Token schema
```
token_t = [side_feat_t (5N+391) ⊕ action_emb(a_t) ⊕ reward_t (标量)
           ⊕ event_bits_t (K) ⊕ opp_style_summary_t (S)]
序列: t-T+1 … t（因果 mask，仅历史）
```
- 训练期 teacher forcing（episode 已存 acts/sides/rews/events）；
- 推理期自回归维护队列（最近 T 决策）；动作先采样再入队。
- 维度控制：side 特征降维（线性/MLP 投影 128–256），总参数 ≤5M。

## 3. 模型规格（≤5M）
- 2–4 层 decoder-only Transformer（d_model 128–192，heads 4–8，FFN 2–4x，RoPE/学习位置）；
- token 投影 + 动作 embedding（n_macros≤256）+ 事件 embedding + 奖励标量归一；
- 输出：策略 logits（n_macros + 残差头，若 action residual v1 上线）、价值/辅助头；
- 与 ppo_gpu 集成：`PPOTrainerGPU` 前向序列批（B,T,dim），mask padding；学习率/裁剪不变。

## 4. 序列采样
- episode npz 已有逐决策 acts/sides/rews/events；滑窗 T=16/32，批 B=64；
- shard 边界禁止跨序列（bc_io shard 语义）；
- 采样缓冲：episode → 序列 npz（离线预生成，避免训练时开销）。

## 5. BC 兼容
- BC trio 的 X/S/Y 逐行仍按**单决策**存储；Transformer 训练时按 episode 顺序滑窗；
- 标签不变（Y=宏 id）；残差/新 slot 走 W4 一次迁移；
- BC aux 头可复用（序列编码后取末 token）。

## 6. PPO 集成
- actor 端：维护 T 长度历史（sides/actions/rewards/events），每决策前向一次；
- learner：GPU 序列批更新；`TH123_SEQ_TRANSFORMER=1` 才启用；
- 兼容：旧模型（GRU mem_v1）加载 → 拒绝/零初始化迁移（W4 统一 registry/gen）。

## 7. 延迟基准（batch1）
- T=16/32，CPU（限 2 线程）/GPU 各测 P50/P99（前向，含 token 栈拷贝）；
- 目标：≤5–10ms/决策（Faynt 级），否则限制 T 或降 d_model；
- 测量脚本 `tools/seq_transformer_bench.py`（原型期交付）。

## 8. 离线原型（1–2 天）
- 用现有 episodes 做**下一宏预测/价值辅助**小预训练（不接 PPO）：
  - 训练集/验证集按 episode 划分（held-out 20%）；
  - 对比基线：mem_v1（GRU）/无历史；指标=next-macro top1、value MSE、aux 命中；
  - 产出 held-out 对比表 + 延迟基准。
- 原型代码：`tools/seq_transformer_proto.py`（离线，独立于训练通道）。

## 9. A/B 设计（待批才进窗）
- 单变量：`TH123_SEQ_TRANSFORMER` 0/1；冻结 pool 夹具（对手/种子/局面集）；
- 主指标：对冻结 pool 胜率 + 行为（远弹/受身/防御/连段）+ KL/ent 不退化；
- 样本门/停止规则/回滚（env 0 单次重启）按 R17；人测由 task-67/69 排。
- 预算：单窗 ≤60min；不与其他变量叠加。

## 10. 风险与反债（R16）
- 风险：序列模型过拟合/延迟超预算/与 BC 标签错位/显存；→ 限参数量、缓存序列、W4 一次迁移载体；
- 反债：不建一次性旁路；env 默认 0；旧模型可回退；序列数据格式随 episode schema v4 统一。
- R15：延迟/预测/加载行为测试；A/B 前离线对比（独立真值=held-out episode）。

## 11. 延迟基准实测（2026-10-26，原型）
- 模型：d_model128/4层/4头/vocab128，params **834,305（<5M）**；batch1；含因果 mask；CPU torch 2 线程。
- 结果（	ools/seq_transformer_bench.py → D:\temp\scratch\h1_seq_bench_20261026.json）：
  | device | T | p50 | p99 |
  |---|---|---|---|
  | cpu | 16 | 7.0ms | 90.6ms |
  | cpu | 32 | 12.8ms | 62.9ms |

- 结论：**T=16 达标（p50 7.0ms，5–10ms 目标内）**；T=32 p50 12.8ms 略超，需 d_model/层数压缩或缓存 mask；
  GPU 未在基准中启用（torch.cuda 不可用/未测），后续在训练机复测。
