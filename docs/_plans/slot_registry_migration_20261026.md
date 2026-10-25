# Slot Registry 一次迁移设计（W4；task-63/64，2026-10-26 草案）

> 用户裁定 A：**暂缓 task-55 B 窗**；3 个 B 宏（623C/22B/214C）+ 移动宏扩充并入
> **slot registry 一次迁移**；不先做 88→91 小迁移。
> 验收合同：`docs/_audit/w4_slot_registry_audit_20261026.md`（W4-1..10）+ C1/C2/C3 合同 +
> R15/R16/R17。本文逐条映射 AC、证据文件、成本/风险/回滚/反债；**未部署**。

## 0. 设计摘要
- **n_out 固定容量 C=256**（先评估后最终定）；现有 id 0..N-1 **身份映射保持不变**；
  新宏只追加到空 slot；空 slot 恒 mask；模型输出层一次扩列零填；之后新增宏只改 registry。
- **Registry Manager** 为唯一写入通道（CRUD+严格 replay+独立真值+版本发布），禁旁路脚本注入。
- **Executor Continuation** 永久子系统（状态条件续段/派生，schema/版本化/hit_mem 整合/
  env 门控；数据来自离线 Discovery），**不改变动作空间**（宏 id 内扩展执行）。
- **Episode schema v4**：显式 `valid_mask`/`registry_hash`/`schema=4`；旧 v3 兼容读/拒绝策略。
- 迁移 = 一次窗（30–60min）+ 回滚演练；之后加宏零迁移。

## 1. 容量评估（C）
### 1.1 现有规模（实测模型参数）
| 角色 | 总参数 | n_out | W_side(n_side×n_out) | W2 | W_mem/64×n_out | 其他 |
|---|---|---|---|---|---|---|
| reimu | 633,241 | 88 | 831×88=73,128 | 128×88=11,264 | 5,632 | W_gru/W_opp/Ws2/b2… |
| marisa | 646,653 | 95 | 866×95=82,270 | 128×95=12,160 | 6,080 | 同上 |
| suika | 638,929 | 91 | 846×91=76,986 | 128×91=11,648 | 5,824 | 同上 |
### 1.2 C=256 影响（解析估算）
- 每角色新增参数 ≈ `(n_side + 128 + 64 + 16 + 64 + 16 + 1 + ...) × (256-N)`
  ≈ 约 **+19–20 万参数**（约占现模型 30%），3 角色合计 < 0.6M → 显存 <10MB(fp32)；
- 前向输出层 MAC：W_side 831×256≈213k vs 73k（+140k），但 conv 主干远大于此 → 预计
  吞吐影响 **<5%**（需 W4-8 固定 batch 基准实测，超阈值回退/降 C）；
- 候选容量：C=128（+40 槽，够 1–2 年）/C=256（+165 槽，长期）。**建议 C=256**，
  以 8/16 对齐；若吞吐超阈改 128（一次迁移后仍可再评估，但避免二次迁移优先选 256）。
- 容量基准项（W4-8 证据）：params/VRAM/前向 P50/update P50（固定 batch/seed），迁移前基线表。

## 2. Registry schema（`models/macro_registry.json`）
```json
{"schema": 1, "char": "reimu", "capacity": 256,
 "registry_version": 3, "content_hash": "sha256:...",
 "slots": [
  {"id": 45, "name": "连段A", "kind": "combo", "status": "active",
   "script_ref": "CHAR_LIBS:reimu:45", "script_hash": "...",
   "frames": null, "action_table": null, "owner": "macro",
   "gen": 3, "created": "2026-10-25", "mask_cond": "always"},
  {"id": 88, "name": "移动·44", "kind": "move", "status": "reserved",
   "script_ref": "registry:reimu:88", "script_hash": "...",
   "mask_cond": "ground && neutral"},
  {"id": 255, "name": "", "kind": "empty", "status": "empty"}
 ],
 "policies": {"empty_slot_mask": "always_masked",
              "new_slot_init": "zero_columns+masked",
              "hot_reload": "actor_episode_boundary",
              "reader_mismatch": "reject_or_degrade_loud"}}
```
- **W4-1**：slot 字段齐全；版本/内容 hash；消费方（train/actor/BC/episode）声明；
  热重载 tmp+replace；旧读者遇新版本→拒绝/显式降级（日志）。
- `status`: active/reserved/empty；**reserved=已分配未训练**（masked）；empty=未分配。

## 3. 身份映射（W4-2，P0）
- 旧 id 0..N-1 **identity**：`old_to_new[i]=i`，全量断言表（3 角色）；
- 新槽从 **max(N)** 之后追加；不同角色独立 registry（各自 N）；
- 旧模型/旧 BC/旧 episode 可读；禁止重排/复用/移动旧 id；
- 证据：`tools/registry_identity_check.py` 输出全量 old→new 表 + fixture 读取 PASS。

## 4. 空 slot mask / 新槽初始化（W4-3/4）
- 空/未训练 slot **恒 mask**；采样/日志/logits 不可选；episode 不产生非法标签；
- 模型输出扩列：新列**零初始化**；新 slot 初始 logits=0 且 masked → 旧动作概率不变；
- 证据：mask 矩阵测试（空 slot 选中=0）；固定输入前向对拍旧 logits/mask bitwise；
  新列全零断言；`tests/test_slot_registry_v1.py`（行为）。

## 5. Episode schema v4 + BC 标签（W4-5）
- `schema=4`：显式 `valid_mask`（替代 NaN sentinel）、`registry_version/hash`、
  `n_out/n_macros/schema` 字段；写者+读者双端校验；
- 旧 v3 读：无 registry → 兼容读（n_out 旧值，registry_hash=legacy）；或明确拒绝+迁移；
- BC：旧 Y 标签 id 不变；新宏标签仅在其 slot 有数据后写入；空 slot 永不进 BC；
  标签映射表版本化（`bc_label_map_v4.json`）；
- 证据：旧 episode fixture 读取/新档 n_out；BC 旧档标签不变；跨档加载测试。

## 6. 迁移工具/回滚（W4-6）
- `tools/migrate_w4_registry.py`（唯一迁移入口，幂等/dry-run/backup/journal）：
  1) 读取 registry 候选（旧槽+N 新宏+移动宏）→ 校验 identity/容量/唯一性；
  2) 模型输出层扩列（旧权重逐位保持、新列零）；写 `model_*_w4.npz` +
     `p2w4_backup_<ts>`（硬链/副本）；
  3) BC 标签映射表（旧不变）；空 slot 不写标签；
  4) episode schema v4 迁移工具（旧档只读兼容优先，可批量转 v4）；
  5) snapshot/pool：旧档读兼容或响亮拒绝（禁静默）；
  6) 原子：registry 文件 tmp+replace；模型/BC trio journal（同 task-60 merge 模式）；
  7) 校验：identity/logits/mask bitwise/BC 标签/旧档读取；失败整体回滚。
- 回滚演练：备份恢复+旧代码；窗口内演练一次。

## 7. 移动宏扩充（task-65；W4-7 证据）
- 实测清单（地面/空中移动）：地面 9 / 空中 6（44/66/冲刺/飞翔/大跳/HJC/空中后跳…）；
- 每个宏：输入序列（真实帧 golden）+ 目标 action/帧表/位移/结束状态；独立真值（手动/盲采）；
- 严格 replay 判据：位移≥阈、结束状态正确、无受击/无空挥；不合格不入 registry；
- 产出 `docs/_plans/movement_macros_20261026.md` 清单（名称/脚本/帧/golden/验证结果）。
- R15：golden 行为测试+变异（删/错标签→红）；禁止仅串断言。

## 8. 热重载（W4-1/6）
- registry 文件原子替换；actor **局边界**读取新版本（校验 hash/version）；旧 actor 保留旧版直到局末；
- learner 使用版本与 snapshot 绑定（meta.registry_version）→ 训练一致；
- 半状态/读者旧版：拒绝并响亮日志；episode contract 带 registry hash；
- 证据：热重载测试（版本切换/旧读者拒绝/hash 一致）+ 启动 manifest。

## 9. 容量/吞吐基准（W4-8）
- 固定 batch（如 256×14400）+ 固定 seed：前向 P50/P99、update P50、VRAM、params；
- 迁移前后对比；阈值：显存 +<300MB、吞吐下降 <10%、P99 <2×迁移前（初定，auditor 可调）；
- 超阈值触发回退（C 改 128/暂缓）并写 decision log。

## 10. AC 映射（W4-1..10 → 证据文件）
| AC | 设计章节 | 证据文件/命令 | 判据 |
|---|---|---|---|
| W4-1 | §2/§8 | `models/macro_registry.json`、`tests/test_slot_registry_v1.py`、热重载日志/启动 manifest | slot 齐全/hash/热重载原子/旧读者拒绝 |
| W4-2 | §3 | `registry_identity_check` 全量表+fixture | identity 100% |
| W4-3 | §4 | mask 矩阵测试+采样测试 | 空 slot 选中=0 |
| W4-4 | §4 | 前后模型对拍（固定输入） | 旧 logits/mask bitwise diff=0；新列零 |
| W4-5 | §5 | schema v4 测试+旧档 fixture+BC 映射表 | 旧档可读/标签不变/新档 n_out 正确 |
| W4-6 | §6 | 迁移 dry-run/备份 hash/回滚演练/等价报告 | 幂等/回滚复现/无半迁移 |
| W4-7 | §7 | movement macro golden+独立真值+变异 | 每宏行为 PASS/变异红 |
| W4-8 | §9 | 容量基准报告（params/VRAM/P50/P99） | 阈值内/有回退触发 |
| W4-9 | §11 | 设计+槽分配表+治理流程 | 未来仅 registry，无新迁移脚本 |
| W4-10 | 全篇 | 门禁输出+C15 登记 | 行为/契约证据，无装饰 PASS |

## 11. 反债评估（R16）
- **为何一次迁移后不再迁移**：空槽容量预留（C=256）+ registry 数据驱动；新宏/派生只写
  registry（slot 数据+zero-init 列）→ 不改网络宽度；移动宏/B 宏本次一次并入，避免
  "88→91 再迁移"。
- **Rejected alternatives**：D1（复用旧 id 动态槽=语义混淆）、D2（executor 快补丁=路径分叉）、
  多次小迁移（每次模型/BC/episode 全链迁移=债）。
- **治理**：Registry Manager owner/版本/审计；transition env（如 `TH123_REGISTRY=legacy`）
  登记到期日+移除 Wave；迁移脚本唯一入口，禁新一次性脚本。
- **预留**：C=256 中 reserved 槽位策略（按角色/用途分段），版本化分配表，防槽位冲突。

## 12. 风险与回滚
| 风险 | 级别 | 缓解 |
|---|---|---|
| 旧 id 重排/复用 | P0 | identity 全量断言+fixture；禁重排 |
| 输出扩列非零/未 mask | P0 | 零初始化+空槽恒 mask+前向对拍 |
| 空 slot 进 BC/episode 标签 | P0 | 标签映射表+校验；BC 构建端过滤 |
| 热重载半状态/旧读者 | P1 | 局边界+版本拒绝+contract hash |
| 迁移非原子/无回滚 | P1 | journal/备份硬链/回滚演练 |
| 移动宏同源自证 | P0 | 独立真值+golden+变异红（R15） |
| 容量/吞吐超阈 | P1 | 基准阈值+回退到 C=128/暂缓 |
| 反债不足 | P1 | W4-9 治理+owner/版本/审计 |

## 13. 阶段与窗口
1. **W4 设计评审**（本文+AC 映射）→ Lead 审 + auditor 按 W4-1..10 复核（不通过不迁移）；
2. 离线实现：registry schema/Manager/identity 检查/模型扩列工具/移动宏 golden/行为测试；
3. 迁移窗（30–60min）：dry-run→备份→迁移→门禁→重启→验收（identity/logits/mask/BC/episode/
   capacity）；回滚演练；
4. 迁移后：C=256 空槽预留；新宏/派生仅 registry；B 窗取消（并入本次）。
**不阻塞**：10-26 10:30 UKEMI / 15:00（BC 锚若复审通过）/ 10-27 其它。
