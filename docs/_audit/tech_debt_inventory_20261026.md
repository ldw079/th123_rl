# 技术债清单（task-64，2026-10-26 起草；只读审计）

> **基线**：HEAD `e09730d`（含 gate R15 phase-2 清理 738/0/0）；审计时刻 2026-10-25 22:0x +08:00；只读，不动训练/代码。
> **方法**：R15 用户红线（`docs/audit_protocol.md` §四）：以行为基座/独立真值评估，不做装饰性审计；每项给证据/影响/严重度/维护成本/重构建议+优先级。
> **状态**：P0 候选 3 项已给 Lead 夜检；完整清单 24–48h 内分批补齐（优先 P0/P1）。明日 UKEMI/BC 锚/B 窗不受影响。

## 0. 最可能导致下次事故的 3 项 P0 候选（Lead 22:30 夜检）

### P0-C1 制品/BC 多格式多一次性迁移 + 代际锚不一致
- **证据**：
  - 模型制品族：`model_ppo*.npz` 30+ 文件，含 plain / `_fleet` / `_fleet_v` / `_pre_space_v1` / `_pre_p1gen1` / `_exploit` / `.stale63`；同角色多代际并存（如 reimu fleet 2.54MB vs plain 2.50MB、pre_p1gen1 2.93MB）。
  - **plain 与 fleet meta 不一致**：plain 旧档 meta `[temp=2.0,beta=0.02,...]`，fleet 现档 `[temp=0.8,beta=0.001,...]`（10-25 21:57）→ 旧 `plain` 路径若被 eval/池/回退加载 = 行为语义不同。
  - BC 制品：`bc_*_X/Y` mtime **10-18**，`bc_*_S`/`meta` mtime **10-23**（跨代际混存）；`[bc_io] trio代际不一致` 日志出现 **8 次**（actor/learner）。
  - 迁移/一次性脚本 **9 个**：`migrate_style_b.py`、`migrate_bc_b.py`、`migrate_gen2.py`、`migrate_p1gen1.py`、`migrate_s2_343.py`、`migrate_feat_space_v1.py`、`bc_label_migrate.py`、`migrate_macros_wave.py`、`verify_gen2_equiv.py`。
  - 事故史：plain 未同步致 P1；池旧快照维度守卫拒载→回退生产；BC 822/831 宽度混代际；`.stale63` 残档仍在目录。
- **影响**：静默加载错误代际/宽度的模型或 BC（训练/评估/池/人测），指标"绿"但语义错；回滚/复现不可靠。
- **严重度**：**P0 候选**（已发生类 P1，下一次可致训练语义污染）。
- **维护成本**：高（制品多、脚本一次性、无注册表）。
- **建议**：制品注册表（gen/width/hash/父版本/用途）+ 加载器生成契约强校验（不匹配响亮拒绝）+ 原子替换/备份/回滚；退役 `_pre_*`/`.stale63` 仅保留备份；一次性迁移脚本收敛为 `tools/migrations/` 带输入输出/等价测试。
- **优先级**：**P0-重构（第一优先）**。

### P0-C2 环境变量动物园（98 个 TH123_*，51 个跨模块重复）
- **证据**：
  - 全库 `TH123_*` 名 **98 个**，其中 **51 个被 ≥2 模块读取**；例：`TH123_BUFFER_NAMES/K/MAXWAIT` 同时由 `game_gates.py` 与 `buffer_primitives.py` 解析；`TH123_STORE` 在 30+ 脚本重复；`TH123_BUFFER_UKEMI_DIR`、`TH123_FEAT_*`、`TH123_GEN2` 分散。
  - 默认/校验/文档不一致：C1/C2 熵窗 `beta_min` 在 C2 启动行回退 0.001（C1 的 0.01 未同时设置）；plain/fleet 模型 meta 默认值不一致；大量 env 无启动校验/无回滚清单。
  - 行为证据：C1 beta=0.01 无效（C2 才靠 temp 生效）；plain 未同步；env-only 变更需要人工记忆参数组合。
- **影响**：同一进程内 actor/learner/tool 读到不同默认或不同来源 → 特征/宽度/mask/温度静默错配；下次事故大概率来自"某个 env 没同步/默认回退"。
- **严重度**：**P0 候选**。
- **维护成本**：中高（改一处需全库搜、文档/launch 需同步）。
- **建议**：中央 `runtime_config.py`（schema：名称/类型/默认/允许范围/消费者/回滚），启动时校验并打印 effective manifest；actor/learner/tools 只读同一入口；launch.bat 生成 manifest 入日志；未知/冲突 env 响亮失败；逐步淘汰重复解析。
- **优先级**：**P0-重构（第二优先）**。

### P0-C3 Gate/mask 单体状态机 allow 叠加
- **证据**：
  - `game_gates.py` 268 行，单函数 `apply_state_gates` 叠：`DOWN_ACTS/HIT_ACTS/GUARD_STUN/AIR_DEF/MISGUARD` 状态集、`BUFFER_NAMES/UKEMI_DIR_TOKENS/GUARD_CANCEL_NAMES` allow 并集、`DD_GUARD_ONLY/AIR_GATE/IMMOBILE_GATE` 开关、埋点计数器。
  - 近期事故：窗#9 `getattr(self._buf_cnt,0)` 笔误致 actor 崩-loop（commit `a8d23cb`）；confirm gate 语义 P1（无行为测试，审计#8已报）；A′/C1/UKEMI 多轮都在同一文件叠加。
  - 行为测试覆盖：近期才补 `test_executor_hitmem_v1` 等；多数状态组合无真实帧 golden。
- **影响**：一条 allow 集合/状态 id 写错即改变动作空间或崩 actor；崩溃/静默错误都可能，且影响三 actor。
- **严重度**：**P0 候选**（刚发生 P1，结构上易复发）。
- **维护成本**：中（文件集中但状态组合多）。
- **建议**：拆为"状态 resolver + allow 表生成器"；每个状态（down/hit/guard/airdef/misguard）独立纯函数 + 真实帧 golden（frozen/hit/blocked/whiff）；env 组合矩阵化测试；禁止字符串断言。
- **优先级**：**P0-重构（第三优先）**。

## 1. 其余技术债（初步，24–48h 补齐）

| # | 项 | 严重度 | 证据（初） | 影响 | 建议/优先级 |
|---|---|---|---|---|---|
| D | Episode schema/NaN sentinel/契约散落 | **P1** | `episode_core.py` schema/宽度/行数对账；`train_tm` `logps NaN` buffer skip sentinel；`learner_hub`/`bc_io` 各自 width 检查；822/831 与 failed/ 隔离已发生 | 半截/混代际 episode 可污染训练或静默丢弃 | 单一 schema 模块 + producer/consumer 契约测试；**P1** |
| E | PPO 双实现漂移（numpy vs torch） | **P1** | `ppo.py` 1071 行 vs `ppo_gpu.py` 1002 行；历史 bug 只在单侧修（mem H、W1v、KL clamp、ratio clamp）；无跨实现 golden | 训练/评估/回放数值语义不一致 | 共享数值规格 + 小批量 golden 对拍；numpy 仅保留离线工具或退役；**P1** |
| F | 特征层魔术索引/弃用段/预留槽（308–315） | **P1** | `feat_builder.py` CORE_DIMS 358/382/391、预留槽位、`LOW_ATTACK_IDS`/`F_VARIANT_IDS` 迁移注释；历史静默覆盖 | 特征错位难发现，模型输入语义漂移 | 生成索引映射表 + schema 测试（维度/偏移/含义）；**P1** |
| G | 奖励层多 env 开关缺语义测试 | **P1** | `atk_v1.py`/rew env 参数多；audit 中多为串检查；R209 前后行为归因困难 | 奖励 bug 表现为"策略不学"，难定位 | 每个 reward 开关行为测试（固定轨迹 rewards 断言）；**P1** |
| H | BC 数据层 hand 迁移/补锚 | **P1**（与 C1 部分重叠） | `bc_build/bc_io/bc_label_migrate` + trio 手写验证；补锚将新增合成锚 provenance | 标签/代际/分布错误污染 BC | 统一 BC pipeline（生成/校验/provenance/cap）；**P1** |
| I | 运维 launcher/WMI/schtasks/autorecover 手工流程 | **P1/P2** | `launch*.bat`/`train_start`/`train_detach`/supervisor 重启；19:59 全灭事故（Job Object/相对路径）；当前仍手工窗 | 停训/整树被杀/回滚慢 | 单一 launcher + 健康门/自动恢复 runbook + 窗验收集成；**P1** |
| J | 文档漂移（门禁数/HEAD 手改） | **P2** | AGENTS/HANDOVER/README 数字曾不一致；本轮 gate 清理后需同步 | 误导验收 | 生成式状态段（门禁/HEAD/变异数自动写入）；**P2** |
| K | Gate 埋点/指标语义漂移 | **P1** | `masked/masked_choice/gate_removed/pref_removed_mass` 口径演进；旧 `masked=` 已废 | 验收口径混淆 | 指标注册表（定义/分母/生命周期/废弃标记）；**P1** |

## 2. 审计方法/R15
- 所有"已发生/风险"结论带文件/行/日志证据；无行为基座的纯串断言不纳入通过项。
- 重构建议必须可验证：行为测试/独立真值/回滚路径；不做装饰性清单。
- 本清单分两批：**批1=P0 候选 3 项（本文）**；批2=其余 10 项逐项证据/成本/路线（24–48h）。
