# P0-C1 重构验收判据（制品/BC 代际治理；草案）

> **状态**：草案（2026-10-25 22:2x）；基线 HEAD `e09730d`；只读审计，不实施。用户红线（2026-10-25"禁止添加无意义自检与门禁"）+ R15：每条验收必须行为基座/独立真值；纯串/装饰断言不计通过。
> **通用通过规则**：AC 必须绑定证据（命令+原始输出/文件/日志）、自动化门禁、可回滚；未列证据=未通过；任何豁免需 Lead 书面批。

## 目标
消除"静默加载错代际/宽度制品"风险：模型制品（plain/_fleet/_v/_pre_*/snap/pool）与 BC 数据（X/Y/S/meta）由**注册表+强校验+可回滚迁移**治理。

## 验收判据（AC）
| ID | 判据 | 证据/测试 | 通过标准 |
|---|---|---|---|
| C1-1 | **制品注册表**：机器可读 manifest，字段 gen/width/hash_sha256/parent/purpose/status(active/archived)/created_by | manifest 文件 + 注册表校验脚本 + 审计抽样 | active 制品 100% 有记录；无未登记 active 档 |
| C1-2 | **加载器强校验**：所有 load 经注册表 API，校验 gen/width/hash；不符→**响亮拒绝**（错误码+消息），禁止静默 fallback；允许回退须显式策略并日志 | 负例测试：错 gen/错 width/错 hash/缺失；日志断言 | 4 类负例均拒绝且不加载；无静默回退路径 |
| C1-3 | **plain/fleet/snap/pool 一致性规则**：用途矩阵（train/eval/pool/control/offline）；meta 三代一致（模型 meta/BC trio/episode schema）；active fleet 只加载同 gen | 一致性检查脚本 + 矩阵文档 + 抽样 | 矩阵 100% 定义；跨 gen 加载=0（显式允许并登记除外） |
| C1-4 | **BC trio 代际校验**：X/Y/S/meta 同步（行数/宽度/hash/时间戳）；加载/换装前统一 verify；`[bc_io] trio代际不一致` 日志→0 | verify 工具 + 好/坏 fixture + 24h 日志扫描 | 好 fixture PASS；坏 fixture 拒绝；24h mismatch=0 |
| C1-5 | **迁移脚本收敛+等价测试**：一次性脚本收敛 tools/migrations/，idempotent、dry-run、备份、原子替换；旧档读兼容/非破坏；旧→新等价 | 迁移清单 + dry-run + 等价测试（数值/行为） | 每条可重复/dry-run/等价 PASS/可回滚 |
| C1-6 | **stale/pre_ 退役**：备份后归档（保留回滚）；active 目录仅注册表 active；恢复演练 | 归档清单 + 恢复演练日志 | active 无 stale/pre_；恢复 PASS；回滚步骤可执行 |
| C1-7 | **R15 行为基座+事故回归**：plain 未同步 P1（行为差应被 gen/用途规则拒绝）；822/831 混代际（拒绝或显式迁移）；trio mismatch；变异→行为测试红 | 真实帧/前向对比行为测试 + 变异记录 | 事故回归全绿；删规则/换标签→行为红；仅串红不算 |
| C1-8 | **验收自动门禁**：registry/loader/trio/migration 检查入 C15/窗验收；PASS 只来自行为/契约检查 | 门禁输出+C15 登记 | 新增检查通过；无装饰 chk |

## 分批
M1 注册表+加载器强校验 → M2 BC trio verify → M3 迁移收敛/归档 → M4 事故回归+门禁接入 → 影子只读期（24h 零静默）→ 强制生效。
