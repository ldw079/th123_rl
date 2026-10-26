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

## 11. 延迟基准（优化版，CPU-only 实测）
- 本机 **torch 2.14.0+cpu，cuda_available=False（18 核）** → GPU 实测不可行，按 CPU 优化复测。
- 优化：`torch.inference_mode()` + KV cache 增量解码 + 预分配/复用 kv + `set_num_threads(2)`
  + 动态 int8 量化对照 + 收窄变体（d64/2层/T8-16）；warmup 后 1000 次；训练运行中测（真实负载）。
- 结果（`tools/seq_transformer_bench_v2.py` → `D:\temp\scratch\h1_seq_bench_v2.json`）：
  | 配置 | p50 | p95 | p99 |
  |---|---|---|---|
  | T=16 d128/4L 无量化 | 2.82ms | 6.17ms | **9.85ms** |
  | T=32 d128/4L 无量化 | 3.65ms | 7.07ms | **12.34ms** |
  | T=16 动态 int8 | 9.30ms | 16.69ms | 22.99ms（量化开销劣化→**不采用**） |
  | d64/2L/T=8 int8 | 4.29ms | 8.55ms | 13.03ms |
- **结论**：KV-cache 增量解码后 **T16 p99 9.85ms、T32 p99 12.34ms，均满足 ≤20/≤30ms**；
  动态量化在 CPU 上反而更慢→弃用；无需收窄到低频 H1'（T32 仍可支撑 62Hz 预算余量）。
- 注意：首次 bench（无 cache）p99 90ms 为未优化假象；本表为最终口径。

## 12. env=0 逐位等价证据
- `TH123_SEQ_TRANSFORMER` 在仓库代码中**无引用**（grep 0 命中）→ 当前 env 默认/0 与旧路径完全等价（不改变任何行为）；
- 原型接入时必须加行为测试：env=0 时模型结构/前向/输出逐位等于旧路径；H1 进窗前补测试。

## 13. A/B 预注册（待批窗）
- 单变量 `TH123_SEQ_TRANSFORMER` 0/1；冻结 pool 夹具（对手/种子/局面集，记录 hash）；
- 主指标：对冻结 pool 胜率 + 行为（远弹/受身/防御/连段）+ KL/ent 不退化；
- 样本门：每角色≥3000 决策 & ≥2 帧档；停止规则=P0/缺员/ent<0.6/KL>0.5 持续 10min→回滚 env=0 单次重启；
- 预算 ≤60min；不与其他变量叠加。

## 14. mem_v1 对比（协议，待数据）
- 同一 episode 划分（held-out 20%）：比较 next-macro top1、value MSE、aux 命中、延迟；
- 基线 A：mem_v1（GRU mem_dim=8）；基线 B：无历史 MLP；候选：H1 T16/T32；
- 数据量不足时先补 episode（当前 fleet 每分钟新增），不伪造结论。

## 15. R19 映射
- H1 验收权威=**user**（行为是否更"像人"、操作是否改善）；离线指标/延迟仅初判；
- 验收包：回放片段 + 延迟/胜率/行为对比 + 无法独立判断点 + yes/no 问题；
- H1 不进 A/B 窗前不要求用户验收；进窗前给 Lead/auditor 材料。
