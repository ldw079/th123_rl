# 专家数据心理博弈捕获方案——BC 管线的序列/反重复/风格条件化（2026-10-14）

> 需求来源: 用户问"rep 采集能否考虑高手们的心理博弈（风格动态调整/防预判不重复用招）"→ 分析结论: rep 数据完整保留但 BC 管线丢弃 ~80%（无反重复/无 punish 标注/无序列记忆/仅 2 步历史）→ 用户令"整合为可执行方案"。
> 定位: 变招方案（V-1~V-6）的**专家数据侧镜像**——同一套基础设施在 oracle 重放和 BC 训练两端各跑一份; 与变招方案合批实施摊薄 CORE_DIMS 迁移成本。
> 合规: PLANNING_AGENT.md 三段式。

---

## 0. 现状核验（时点 2026-10-14 10:16）

| # | 项 | 实况 | 心理博弈捕获能力 |
|---|---|---|---|
| 1 | oracle 双边被动观测 | `SOKUAI_OBSERVE=1`, mod 逐帧推 sendState（双边状态包） | ✅ **数据层完整**——高手每次选择+对手反应都在 shard 里 |
| 2 | bc_match.walk() | 贪心匹配, 输出 (帧号, 宏idx, 置信度), 顺序消费 | ❌ **无已用宏记忆**——同一招连匹配 5 次产 5 个相同标签 |
| 3 | bc_build 行构建 | `build_rows()` 逐帧 → 侧向量含 last_macro + last_macro2（2 步） | ❌ **无序列特征**（无 streak/entropy/换招标记） |
| 4 | shard meta | `np.savez` 带 meta dict, EP_SCHEMA=2 已支持扩展 | ✅ **可扩展**——加字段走 schema 版本升级 |
| 5 | oracle_batch2 | 已存 ilog（输入日志）+ pkts（状态帧） | ✅ 可在重放/后处理时对双边跑 punish 追踪 |
| 6 | 训练侧 BC 消费 | `_sample_bc(k=64)` 随机采 64 行, iid, bc_extra 混入 PPO | ❌ **iid 采样**——连续帧的"换招模式"被打乱 |
| 7 | CORE_DIMS | **330**（R61t 后） | 本方案追加特征需 +N → 336+（与变招方案 V-1/V-2 的 +6 合并为 +12, 一次迁移） |
| 8 | GRU | 未实现（系列方案阶段 3 / 变招方案 V-3, 已有完整可重放设计） | 合并实施——BC 序列感知与 RL 对手记忆共享同一 GRU |

---

## 1. 方案主体——四件套（编号 P-1~P-4, 与变招方案 V-1~V-6 对齐）

### P-1 · 专家侧 punish 追踪（oracle 重放/后处理, 1.5 人日）

**新增 `tools/expert_punish_track.py`**——对 shard 双边各跑一个 MyPunishTracker（与变招方案 V-1 同一实现, 不同消费者）:

```
输入: shard npz（pkts + offsets + ilog）
输出: 逐帧的双边 punish 状态 → 追加到 shard（或平行文件）
```

**实现路径**: 后处理式（不必重跑 oracle 重放）——读现有 shard 的逐帧状态（HP/动作/位置），按 V-1 的 punish 判定逻辑（我方类别 C 宏执行中 && 对手命中 && 我方未命中 → C 类 punish+1）逐帧推算。已有 191 shard × 双边 = 382 局可追溯处理。

**shard 扩展**（EP_SCHEMA 2→3）:
- `punish_l`: (n_frames,) float——左方各帧的当前 punish_rate 向量（4 类, 展平为 4 列或 dict）
- `punish_r`: 同上右方
- 简化: 每帧存 `(jump_pr, melee_pr, bullet_pr, skill_pr)` 4 float → 8 列/帧（双边）

**验收**: 对已知"被对空 punish"的序列, jump_punish_rate >0.5; 后处理脚本对 3 个 shard 产出非零 punish 列; 行为测试。

### P-2 · BC 行的反重复与换招特征（bc_build 侧, 1 人日）

**bc_build.build_rows() 内**, 在现有 `last_m/last_m2` 基础上追加 6 维特征:

| 维 | 内容 | 归一 | 捕获的心理博弈 |
|---|---|---|---|
| same_streak | 当前标签连续出现次数 | /5, clip [0,1] | **防预判**——"这招用了 N 次了" |
| recent_entropy | 最近 5 个标签的熵 | /log(5) | **多样性**——"出招是否单一" |
| is_switch | 本行标签 ≠ 最近 3 个标签的众数 | 0/1 | **换招标记**——"这是变招" |
| opp_punish_my_dominant | 对手 punish 我方当前主导类的率 | [0,1] | **被反制感知**——"他在防我这套" |
| opp_style_atk | 对手当前攻击性份额（opp_model 3 维摘要之一） | [0,1] | **风格评估** |
| opp_style_mob | 对手当前机动性份额 | [0,1] | 同上 |

- 前 3 维从 matcher.walk() 的输出序列**直接计算**（不需额外数据）;
- 后 3 维从 P-1 的 punish 列 + shard 内状态逐帧跑 opp_model 提取;
- **bc_build 在构建时**需要把 matcher 输出的"帧号→宏idx"序列保留（当前 build_rows 只在 hit_at 查表, 丢掉了序列）——改为维护最近标签的 deque。

**验收**: 合成序列"AAAA B AAAA C"→ same_streak 在 A 段递增, B 处 is_switch=1, C 处 entropy 上升; 特征存在且非恒零/恒一。

### P-3 · BC 训练的序列感知采样（与 V-3 GRU 合并, 0.5 人日增量）

**当前**: `_sample_bc(k=64)` 从全库 iid 随机采 64 行。
**改为**: **连续窗口采样**——从同一 shard 内随机起点取连续 64 帧的 BC 行（保证序列连贯性）, GRU 在 BC 阶段能学到"连续两招相同→第三招该换"。

```python
def _sample_bc_sequence(self, k=64):
    """序列感知采样: 同一shard连续k帧(跳过对齐失败窗)."""
    shard_ids = [i for i, sid in enumerate(self._bc_shard_ids) if sid != -1]
    if not shard_ids:
        return None
    start = rng.choice(len(shard_ids) - k)
    idx = list(range(start, start + k))
    return (X[idx], S[idx], Y[idx])
```

- 需要在 BC 库中额外存储 `shard_id` 列（当前丢失——bc_build 追加）;
- GRU 路径: BC 行按序喂 GRU → 隐状态进策略/价值/aux 输入（与 V-3 的 RL 路径共享 GRU 参数, BC 梯度和 RL 梯度都回流）;
- **BC 锚的角色升级**: 从"教什么招好"升为"教在什么序列上下文/对手状态下用什么招好"——锚的退火路径不变（bcw→0）, 但在退尽之前传输的知识更丰富。

**验收**: BC 库 X/S/Y/Y_seq_id 四键齐; `_sample_bc_sequence` 返回连续 shard_id; GRU 路径 onestep 等价测试覆盖。

### P-4 · 风格条件化的标准树升级（optional, 0.5 人日）

standard_tree 的教义节点按 `opp_style_atk/mob` 分层——"对手偏攻时标准应对 X / 偏防时标准应对 Y"。影响: 审计的偏离矩阵多一个风格维度, 教学讲解（teach.py）可以输出"对手偏攻, 你应偏防"的个性化建议。

**验收**: 树含 ≥3 个风格条件节点; audit 输出含风格分层。

---

## 2. 与变招方案的合并矩阵

| 共享组件 | 变招方案(模型侧) | 本方案(专家侧) | 合并实施 |
|---|---|---|---|
| MyPunishTracker | V-1: train_tm 帧循环追踪我方被 punish | P-1: 后处理对 shard 双边追踪 | **同一 class, 两处调用** |
| punish 特征(+4) | V-1: 侧向量追加 | P-2: BC 行侧向量追加 | **同一 4 维** |
| aux 预测回流(+2) | V-2: 决策点读 aux 头输出 | P-2 的 opp_style 2 维（opp_model 摘要, 非 aux 头——但语义对称） | 分别实施, 合并为 +6 维 |
| GRU 序列记忆 | V-3: RL 对局中的对手序列 | P-3: BC 训练中的专家序列 | **同一 GRU 参数, 双梯度源** |
| CORE_DIMS 迁移 | 330→336（V-1/V-2 的 +6） | 336→342（P-2 的 +6） | **合并为 330→342, 一次迁移** |
| 压力测试 | V-4: 规则反制者测模型 | P-4: 标准树风格分层 | 互补 |

**合并后 CORE_DIMS 330→342（+12 维）, 一次常量横扫**。

---

## 3. 排期（总计 ~3.5 人日; 与变招方案合批后总 ~12 人日）

```
独立可先行:
  P-1 专家punish后处理(1.5d) ← 可立即跑现有191 shard
  P-2 BC反重复特征(1d) ← 依赖 P-1 产物
  P-4 风格条件树(0.5d, optional)

与变招方案合批:
  P-3 序列采样(0.5d) ← 依赖 V-3 GRU 实现
  CORE_DIMS 330→342 ← 依赖 V-1+V-2+P-2 全部就绪, 一次迁移
```

**推荐执行序**:
1. **第一周**: 变招方案 V-1/V-2 + 本方案 P-1/P-2（共 +12 维准备） → CORE_DIMS 342 迁移 → fleet 重启训练
2. **第二周**: V-3 GRU + P-3 序列采样 → onestep 等价扩展 → 二次重启
3. **持续**: V-4 压力测试 + P-4 风格树 → 每周复测 B1-B4 行为涌现

## 4. 风险表

| 风险 | 概率 | 缓解 |
|---|---|---|
| 专家 punish 追踪的归因误差（后处理无 ilog 时判定的宏类别可能与实际不符） | 中 | 优先对有 ilog 的 shard 跑（精确对齐）; 无 ilog 的走互相关对齐的置信度门 |
| BC 序列采样使数据有效量下降（连续帧高度相关, 64 帧可能只覆盖 1-2 个决策点变换） | 高 | k=64 帧非 64 决策——BC 行本就按决策点（hit_at）构建, "连续 64 行" = 连续 64 个决策点（约 1-2 局内）; 随机起点保证多样性 |
| +12 维迁移事故（第 4 次 CORE_DIMS 变更） | 中 | 常量横扫 SOP; learner 派生式在; onestep 等价先行; BC 库 repad 版本守卫 |
| 反重复特征被策略过度泛化（"任何连续都用→回避一切重复"包括合理的连段重复） | 中 | same_streak 特征仅对**类别级**（跳跃/近战/弹幕）而非具体宏——连段 A 内部的 A-A-A 不计入（它们是同一宏的内部步, 非独立决策）; is_switch 也是类别级 |
| BC 锚教了专家的坏习惯（专家偶尔也犯重复用招的错误） | 低 | CONF_MIN=0.92 已过滤低置信; streak>3 的行可作为**负例**（BC 损失取反——"不要这么做"）——列为可选增强 |

## 5. 验收途径

| 项 | 量化阈值 | 测量方法 |
|---|---|---|
| P-1 punish 后处理 | 3 个 shard 产出非零 punish 列; 已知"被对空"序列 jump_pr>0.5 | 后处理脚本+合成测试 |
| P-2 反重复特征 | same_streak/entropy/is_switch 存在且非恒零恒一; "AAAA B"序列 streak 递增+switch 触发 | bc_build 行为测试 |
| P-3 序列采样 | BC 库含 shard_id 列; `_sample_bc_sequence` 返回连续段; GRU onestep 等价 | 单测+onestep |
| P-4 风格树 | ≥3 风格条件节点; audit 含风格分层 | 树结构断言 |
| **总验收（训练后）** | **BC 锚传输+RL 训练 2 周后, V-4 压力测试中 B1-B4 行为涌现率提升**（对比不加盐基线） | 压力测试前后对照 |
| 门禁 | 全绿 + 新断言配对变异 | contract_check + SELFTEST |

## 6. 不变面

- rep 文件与 oracle shard **不重采集**——所有改动为后处理/消费侧扩展;
- StreamMatcher 匹配逻辑不变（反重复特征在 bc_build 层加, 不改匹配器核心）;
- BC 锚退火路径不变（bcw→0）; 奖励结构不变;
- R1-R11 红线 / fleet 三红线 / 单写者 / 门禁纪律全程有效;
- EP_SCHEMA 版本化升级（2→3）走既有拒收机制。

## 7. 用户裁定项

| # | 项 |
|---|---|
| P-4' | 风格条件化标准树是否实施（效果优先推荐做, 但可与前三件解耦） |
| P-5' | streak>3 的 BC 行是否作为负例（"教什么不该做"——与现行 BC 损失取反的实现） |

---
*三段齐备（现状核验 2026-10-14 10:16 / 可执行方案 / 验收途径）, 合规 PLANNING_AGENT.md; 与变招方案合批实施, 一次 CORE_DIMS 迁移覆盖双侧 +12 维。*
