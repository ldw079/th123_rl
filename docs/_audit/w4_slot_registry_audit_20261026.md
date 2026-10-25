# W4 slot registry / 移动宏迁移审计判据（草案；task-63；2026-10-26）
> **裁定背景**：用户选 A——**暂缓 B 窗（10-27）**；B 宏+移动宏扩充并入 **slot registry 一次迁移**（不再单独 n_out 88→91）；迁移窗不早于设计审计通过。
> **基线/状态**：HEAD `5498a7f`；只读；本文件为设计审计合同（待 W4 设计出来后按此复核）。**R15**：所有通过项须行为/契约证据，纯串断言/装饰不计。
> **依赖合同**：`acceptance_c1_artifacts_20261026.md`（制品/注册表/迁移/回滚）、`acceptance_c2_env_20261026.md`（配置单源）、`acceptance_c3_gate_20261026.md`（gate 行为）；W4 必须同时满足，不得以"迁移窗"豁免。

## 0. 范围
- registry：slot 分配/版本/哈希/热重载；旧 id 保持；空 slot mask；模型输出扩列零填；episode/BC 标签兼容；迁移工具/回滚/备份；移动宏 replay 行为验证；容量/吞吐；反债（为何一次迁移后不再迁移）。
- 明确**不做**：不单独 88→91 B 窗；不新增一次性迁移脚本；不以 n_out 变化替代 registry 设计。

## 1. 验收判据（AC）
| ID | 判据 | 证据/测试 | 通过标准 |
|---|---|---|---|
| W4-1 | **registry schema/版本/哈希/热重载**：slot 表（id/name/kind/char/status/frames/action_table）、registry_version、内容 hash；消费方（train/actor/BC/episode）声明；热重载原子（tmp+replace）且旧读者拒绝/明确降级 | schema 文件 + hash + 热重载测试 + 启动 manifest | 每 slot 有记录；加载/热重载失败响亮；旧新 readers 行为一致或显式拒绝 |
| W4-2 | **旧 id 映射保持**：现有宏 id 0..N-1 **身份映射**；新 slot 仅追加；映射表 old→new 完整；旧模型/旧 BC/旧 episode 可读；不得重排/复用 | 全量 old id→new 表 + 全宏测试 + fixture | old→new identity 100%；无旧 id 被重排/复用；旧档读取 PASS |
| W4-3 | **空 slot mask**：未训练/空 slot 在 mask/采样/logits 中不可选（或显式空概率），episode 不产生非法标签；mask 测试覆盖全部空 slot | mask 矩阵测试 + 采样测试 | 空 slot 选中=0；旧动作 mask 不变 |
| W4-4 | **模型输出扩列零填等价**：扩列时新列零初始化/零填；旧动作 logits/mask **bitwise** 与迁移前一致（固定 fixture/种子）；新列初始不改变旧动作概率 | 前后模型对拍 + 固定输入前向 | 旧动作 logits maxdiff=0/容差0；mask 逐位=0 diff；新列初始零 |
| W4-5 | **episode contract + BC 标签映射/旧档兼容**：schema 版本 bump；n_out/n_macros/width 显式；旧 episode 读取（零扩/映射）或明确拒绝+迁移；BC 旧 Y 保持、新宏标签定义；跨档加载测试 | schema/contract 测试 + 旧档 fixture + BC 单测 | 旧档可读且标签不变；新档 n_out 正确；无静默错位 |
| W4-6 | **迁移工具/回滚/备份**：registry+model+BC+episode 迁移工具幂等/dry-run/备份（硬链）/原子（trio/模型/registry 级）/journal/回滚；旧→新等价测试（行为/数值） | 迁移 dry-run + backup hash + 回滚演练 + 等价报告 | 迁移可重复；回滚复现旧档；备份 hash 一致；无半迁移 |
| W4-7 | **移动宏 replay 验证（R15）**：每个新增移动宏/B 宏：真实帧 golden（输入序列→action/帧表/位移/结束状态）；独立真值（手动/独立采集）；变异（删/错标签）→行为红 | frame golden + 独立输入序列 + 变异记录 | 每宏行为 PASS；独立真值一致；变异红；仅串红不算 |
| W4-8 | **容量/吞吐**：参数量/显存/前向-更新吞吐/延迟在固定 batch 下与迁移前对比；扩列影响可接受；有回滚阈值 | 容量基准（params/VRAM/吞吐/P50）报告 | 显存/吞吐在事先阈值内；有明确回滚触发 |
| W4-9 | **反债评估（一次迁移后不再迁移）**：slot 分配策略+预留容量+版本治理；新宏/移动宏未来如何加入（仅 registry 数据，不改网络/迁移）；明确不再出现"88→91/再迁移" | 设计文档 + 分配表 + 治理流程 | 未来新增仅 registry；无新增一次性迁移脚本；有 owner/版本/审计流程 |
| W4-10 | **AC/R15 接入**：C1/C2/C3 合同项+本判据纳入 C15/窗验收；删装饰断言；证据可审计 | 门禁输出+C15 登记 | 通过项均有行为/契约证据；无装饰性 PASS |

## 2. 必测矩阵
- 旧宏：全量 old id（88/95/91）→ 新 registry 读取/前向/mask/BC label/episode 读取。
- 新宏：每个新 B/移动宏一条真实帧 golden + 独立输入基准；空 slot 全 mask。
- 模型：迁移前 vs 迁移后固定输入（logits/mask bitwise、value 不变）；旧 checkpoint 加载。
- 数据：旧 episode（width/n_out 旧）→ 读取/迁移；BC trio 旧档→标签映射；pool/snap 旧档→拒绝/迁移。
- 部署：dry-run→备份 hash→原子迁移→回滚演练。

## 3. 风险清单
1) 旧 id 重排/复用 → 旧模型/BC 语义漂移（P0）。
2) 输出扩列非零初始化/未 mask → 新 slot 被随机选中（P0）。
3) 空 slot 进入 BC/episode 标签 → 数据污染（P0）。
4) 热重载半状态/读者旧版 → 运行错配（P1）。
5) 迁移非原子/无回滚 → 半档（P1）。
6) 移动宏 replay 同源自证 → 假绿（P0，R15）。
7) 容量超阈值未评估 → 吞吐/显存退化（P1）。
8) 反债不足 → 下一宏再迁移（P2/P1）。

## 4. 复核流程
设计稿到→按 W4-1..10 出 PASS/FAIL 表（证据/命令/样本）；不通过项施工修正；实现后按同表复审；通过后 Lead 定迁移窗（不早于设计通过）。本审计只读，不实施迁移。
