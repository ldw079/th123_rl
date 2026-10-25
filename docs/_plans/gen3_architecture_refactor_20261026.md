# Gen-3 架构重构路线图（task-64 + task-63 合并，2026-10-25 草案）

> 状态：设计草案（只读；未改代码）。基线 HEAD=`e09730d`（+ 今晚未提交的 BC 锚工具/文档）。
> 用户令（2026-10-25）：**目的=超人模型，不积攒技术债，永远选长期维护有利方案**；
> 短期权宜须显式批准+附移除计划（**R16 红线**，已写入 METHODOLOGY/HANDOVER，本文件含反债评估）。
> 验收：auditor 三份 AC 合同（`docs/_audit/acceptance_c1_artifacts_20261026.md`、
> `acceptance_c2_env_20261026.md`、`acceptance_c3_gate_20261026.md`）+ R15（行为基座/独立真值）。

> 代码地图/env 统计/事故映射见 **docs/_plans/gen3_appendix_codemap_20261026.md**
> （98 个 TH123_* 唯一名、62 个跨文件重复名；关键模块/事故→债务映射）。

## 0. 结论与总路线
| Wave | 主题 | AC 合同 | 目标 | 风险 | 窗口 |
|---|---|---|---|---|---|
| W1 | 制品/BC 代际治理 | C1-1..8 | 注册表+加载器强校验+trio verify+迁移收敛+stale 退役 | 低（离线+只读期） | 设计+离线先行；不阻塞现有窗 |
| W2 | 配置单源 | C2-1..8 | `runtime_config.py` 单源+manifest+冲突失败+默认 bit-equal | 中（触及所有模块读取） | 逐模块收敛，独立可回滚 |
| W3 | Gate 状态 resolver | C3-1..7 | 声明式 resolver+allow 表+真实帧 golden+mask 逐位等价 | 中高（行为面） | 先 golden/对拍，再拆 |
| W4 | Episode schema v4 + 宏库长期架构 | 本文件 §4 + task-63 | 显式 valid mask/registry hash/slot registry/Continuation/Discovery/Memory Bank | 中（一次迁移） | 用户批后单独窗 |

**原则**：每 Wave 独立可回滚、不破坏训练；先影子/对拍→再强制；AC 未过不合并；禁一次性 hack。
**当前不做**：不改 C1/C2/C3 生产代码（用户令：今晚/明日不改）；只做只读清单/设计。

## 1. 现状债务地图（审计输入）
### 1.1 C1 制品/BC（现有证据见 `D:\temp\scratch\c1_artifacts_inventory_20261026.md`）
- 模型制品 **68 npz**：plain（部分 pre-GEN2 宽 5N+358）/fleet（5N+391）/`_v`（keys=6、meta 空）/
  exploit；snap_*（含 `_pre_space_v1` 旧代）；pool_*（legacy 空）。用途矩阵未声明。
- BC：trio `X/S/Y/meta` 当前**哈希/行数/宽度全部一致**（已用 `bc_io._arr_sha256` 验证）；
  但 `data/bc/bc_*.npz` 为**旧代 npz（S 宽 680/710/715）**，`bc_io.find_bank` 在 store 缺失时可
  **静默回退**→旧代误载风险。
- 一次性迁移/修复脚本 **9 个**（migrate_style_b/bc_b/bc_label/gen2/p1gen1/feat_space/s2_343/
  macros_wave + bc_meta_resync）：缺 idempotent/dry-run/等价测试统一框架。
- 历史事故：plain 未同步 P1（行为差）、822-831 混代际、BC trio meta 哈希不一致（已修但无强校验）。
### 1.2 C2 配置
- `TH123_*` 约 **98 个**、**51 个跨模块重复**（auditor 数据）；默认/类型/范围未单源声明；
  启动无 effective manifest；冲突静默取一。
### 1.3 C3 Gate
- `game_gates.apply_state_gates` 单体 allow 叠加；状态 id 散落；env 组合矩阵无覆盖；
  真实帧 golden 缺；`_buf_cnt`/confirm/UKEMI 事故无回归。
### 1.4 Episode/模型制品 schema
- episode schema v3（hist）但 valid mask/registry hash 未显式；NaN sentinel（buf_skipped）语义散落；
  meta 字段不统一（`_v` 空 meta、snap 无 gen 字段）。
### 1.5 运维/文档
- launcher（WMI/schtasks/autorecover/bat）手工；文档门禁数/HEAD 手改漂移。

## 2. Wave1：制品/BC 代际治理（AC C1-1..C1-8）
**范围**：
1. **模型制品注册表** `models/registry.json`（机器可读）：字段 gen/width/n_macros/hash(parent)/purpose
   (train/eval/pool/control/offline)/status(active/archived)/source/created_at；active 100% 登记。
2. **统一加载器**（`model_loader.py`）：所有 load 走注册表 API；校验 gen/width/hash/用途；
   不符**响亮拒绝**（错误码+消息）；禁止静默 fallback；显式回退策略需日志+登记。
3. **BC trio verify 工具** `tools/bc_trio_verify.py`：X/S/Y/meta 行数/宽度/hash/时间戳一致；
   `data/bc` 旧 npz 归档（备份后）并禁加载（C1-6）。
4. **迁移收敛** `tools/migrations/`：9 脚本统一 CLI（--dry-run/--apply/--backup/--verify）；
   idempotent；旧→新等价测试（数值/行为）。
5. **stale 退役**：pre_/旧代/空 pool 归档到 `D:\temp\th123_models\_archive_<ts>`（保留回滚），
   恢复演练脚本。
6. **事故回归**（R15 行为基座）：plain 未同步 P1（gen/用途拒绝）、822×831 混代际（拒绝/迁移）、
   trio mismatch（拒绝）；变异→行为测试红。
**验收证据**：`registry.json`、`tools/model_loader.py`+负例测试、`tools/bc_trio_verify.py`+
好/坏 fixture、迁移 dry-run 日志、归档清单+恢复演练、`tests/test_model_registry_v1.py`。
**成本**：M1 2–3 人日（离线+影子只读 24h）；**风险低**；**回滚**：保留旧加载路径（env `TH123_STRICT_LOAD=0`
仅过渡、需 Lead 批准+移除计划）；**退出**：24h 零静默回退日志、AC 全过、auditor 复核。

## 3. Wave2：配置单源（AC C2-1..C2-8）
**范围**：
1. `runtime_config.py`：单源 schema（名称/类型/默认/范围/消费者/回滚/env-or-file）；
2. 启动 **effective manifest**（值/来源/schema hash）打印+落盘；launch 日志带 hash（C2-2/C2-6）；
3. 冲突/非法/未知→启动失败（错误码）；别名过渡表（warning+期限）（C2-3/C2-4）；
4. 逐模块收敛：除 schema 外禁直接 `os.environ.get('TH123_*')`（lint 门禁 C2-1）；
5. **默认逐位等价**：固定种子、无 env 下前向/更新 bit-equal（C2-5）；
6. 回滚清单+演练（C2-7）；R15 行为测试（C2-8）。
**成本**：3–4 人日（分 4 批：schema/manifest→重复收敛→等价比对→回滚门禁）；**风险中**；
**回滚**：`TH123_CONFIG_MODE=legacy`（读旧路径）逐批回退；**退出**：51 重复=0（或登记别名）、
bit-equal、三 actor/learner manifest hash 一致。

## 4. Wave3：Gate 状态 resolver（AC C3-1..C3-7）
**范围**：
1. 声明式 resolver：状态枚举（DOWN/HIT/GUARD/AIRDEF/MISGUARD/…）+ allow 表生成器
   （纯函数；禁散落 if 叠加）；
2. 真实帧 golden：每状态 frozen/hit/blocked/whiff/guard/misguard ≥1 条真实帧轨迹（含帧日志来源），
   期望允许集合/最终 mask（C3-2）；
3. env 组合矩阵（ACT_MASK/AIR_GATE/IMMOBILE_GATE/DD_GUARD_ONLY/BUFFER/UKEMI_DIR/GUARD_CANCEL）；
4. **等价对拍**：旧 vs 新 mask bitwise；差异=0 或书面豁免（C3-4）；
5. 事故回归：`_buf_cnt`（a8d23cb）、confirm 语义、UKEMI/buffer/DD 边界；变异→行为红（C3-5）；
6. 随机 fuzz（合法/非法状态）属性测试（C3-7）；禁字符串断言（C3-6）。
**成本**：3–4 人日；**风险中高**（行为面）；**回滚**：`TH123_GATE_V2=0` 切旧实现（保留双实现对拍期）；
**退出**：mask 逐位等价、golden 全绿、事故回归红/绿、fuzz 0 崩溃。

## 5. Wave4：Episode schema v4 + 宏库长期架构（task-63 合并）
### 5.1 Episode schema v4
- 显式字段：`valid_mask`（替代 NaN sentinel）、`registry_hash`、`model_gen`、`schema=4`；
- 契约 v4 校验（写者+读者双端）、旧 v3 兼容读（一次性迁移）；`[ep] schema/version` 日志。
### 5.2 固定容量 slot registry（长期正解）
- `n_out=C`（容量评估：当前 88/95/91；建议 **C=256**，按模型输出层/BC 标签/内存/吞吐评估）；
- `registry.json`：slot→{name, script, version, hash, gen, purpose}；**空 slot 恒 mask**；
  新宏追加占空 slot + 输出层零填（一次迁移后零迁移）；
- 版本化：registry hash 入 snapshot meta + episode contract；**actor 局边界热重载**；
- 迁移工具：输出层扩列（旧列逐位不变/新列零）、BC 标签映射、动作表/宏计数/掩码同步；备份+verify+回滚。
### 5.3 Macro Registry Manager（永久）
- CRUD + 严格 replay 验证 + 独立真值 + BC 锚钩子 + 版本发布（禁旁路脚本注入）；
- 发布门：派生/新宏必须带 provenance（场景/帧/来源）与严格 replay 证据。
### 5.4 Executor Continuation 子系统（永久）
- 通用状态条件续段/派生框架：schema/版本化、与 hit_mem 整合、真实帧 golden trace、
  env `TH123_COMBO_BRANCH=0` 门控；无条件匹配→旧行为；递归深度/超时上限；
- 数据来自 Discovery 管线；不改变动作空间（宏 id 内扩展执行）。
### 5.5 离线派生发现管线（永久）
- 起点宏→中断点状态→枚举候选（方向×按钮×时序）→严格 replay+独立真值→质量/去重/上限
  →入 Registry Manager 候选；
- 记录不合格样例（防止误导）；参数化（场景/宏/深度）。
### 5.6 Combo Memory Bank
- 只读观察状态/动作序列（R1 无输入泄漏审计）；模式库（char/动作序列/伤害/条件/来源）；
  用于防守策略与 Discovery 候选模板。
**成本**：W4 一次迁移窗（模型/BC/统计）+ registry/continuation/discovery 各 1–2 人日；
**风险中**（容量/迁移/漂移）；**回滚**：迁移备份+旧代码；env 门控；**退出**：AC（待 auditor 出 W4 合同）。

## 6. 反债评估（R16 强制节）
- **为什么不是捷径**：取消 D1（低使用 id 动态槽=语义混淆）与 D2（executor 快补丁=路径分叉）；
  统一为 slot registry + registry manager + continuation 子系统，长期零迁移、唯一数据通道。
- **一次性 vs 永久**：W1–W3 收敛现有散落实现；W4 一次迁移换永久扩展；之后新增宏/派生
  走 Registry Manager，禁止再写迁移脚本。
- **禁止项**：旁路脚本注入 registry；静默 fallback；临时 env 双默认；装饰断言；未登记 active 制品。
- **移除计划**：任何过渡 env（如 `TH123_STRICT_LOAD=0`/`TH123_CONFIG_MODE=legacy`/`TH123_GATE_V2=0`）
  必须登记到期日+移除 Wave，超期即门禁红。

## 7. 排期与依赖（不阻塞现有窗）
- 今晚/明日：只读清单（C1 inventory 已交）+ 本设计评审；**不动 C1/C2/C3 生产代码**。
- 10-26：10:30 UKEMI / 15:00 BC 锚部署（现有宏，符合长期架构，后续随 registry 迁移）。
- 10-27：B 窗（既定）。
- 之后：W1 设计评审+离线实现（影子 24h）→ W2 → W3 → W4（每 Wave Lead+用户批）。
- 每 Wave 交付：设计细化+AC 证据清单+离线测试+影子/对拍+回滚演练；auditor 按 AC 复核。

## 8. 三个最可能导致再次事故的债（P0，已获 auditor 接受）
- **C1**（制品多格式/迁移脚本/静默回退；证据：9 脚本、68 npz、旧代 npz 回退路径、历史事故）；
- **C2**（98 env/51 重复/无 manifest/冲突静默；配置漂移已多次造成窗口变量混淆）；
- **C3**（gate 单体 allow 叠加/状态 id 散落/缺 golden；`_buf_cnt`、confirm 语义事故先例）。
优先级：W1 > W2 > W3（W4 与 task-63 合并，独立排期）。

## 9. 需 Lead/用户裁定
1. W4 容量 C（建议 256）与迁移窗时间；
2. 过渡 env 允许清单与移除期限（反债）；
3. W1–W3 各 Wave 是否按本文件顺序推进；
4. 现有 BC 锚（明日 15:00 部署）是否保留为临时通道并登记"随 registry 迁移"计划。
