# P0-C2 重构验收判据（env 单源配置；草案）

> **状态**：草案（2026-10-25 22:2x）；基线 HEAD `e09730d`；只读审计，不实施。用户红线（2026-10-25"禁止添加无意义自检与门禁"）+ R15：每条验收必须行为基座/独立真值；纯串/装饰断言不计通过。
> **通用通过规则**：AC 必须绑定证据（命令+原始输出/文件/日志）、自动化门禁、可回滚；未列证据=未通过；任何豁免需 Lead 书面批。

## 目标
把 98 个 `TH123_*`（51 个跨模块重复）收敛为**单源 runtime_config schema**；启动打印 effective manifest；冲突/缺省不一致响亮失败；默认逐位等价。

## 验收判据（AC）
| ID | 判据 | 证据/测试 | 通过标准 |
|---|---|---|---|
| C2-1 | **单源 schema**：runtime_config 定义名称/类型/默认/范围/消费者/回滚/env-or-file；除该模块外禁止直接 `os.environ.get('TH123_*')`（lint/grep 门禁） | schema + grep 门禁 + 扫描报告 | 业务模块直接读取=0（schema 自身除外） |
| C2-2 | **effective manifest**：启动打印/落盘（值/来源 env-file-default/schema hash）；三 actor/三 learner/tools 同 hash | 启动日志/manifest 文件 | 全部进程同 schema hash；来源可追溯 |
| C2-3 | **冲突/缺省不一致→启动失败**：同名重复默认不同、类型/范围非法、未知 env 策略冲突→退出码非0+消息；禁止静默取一 | 负例测试（冲突默认/非法值/未知） | 负例全部失败；无静默覆盖 |
| C2-4 | **51 重复 env 收敛/别名**：唯一 owner；别名仅过渡（warning+期限）；收敛前后清单 diff | 收敛清单+别名表+扫描 | 重复定义=0（或全部登记别名）；无未登记重复 |
| C2-5 | **默认逐位等价**：无 env 时 effective 值/类型逐项与旧基线一致；固定种子下一步前向/更新输出 bit-equal（容差0或明确） | 基线快照+等价测试 | 值等价 100%；行为 bit-equal |
| C2-6 | **launch 日志含 manifest hash**；窗验收校验 hash 与 schema/配置一致 | launch.bat/train_start 日志+验收脚本 | hash 存在且匹配；缺失=窗验收 FAIL |
| C2-7 | **回滚清单**：每 env 有回滚值/旧行为说明；演练回滚 | 回滚清单+演练日志 | 演练 PASS |
| C2-8 | **R15 行为/契约测试**：配置测试为 import+值/环境行为断言，禁止纯串；关键 env（BUFFER/UKEMI/GEN2/FEAT/VAL/BATCH）行为测试 | 测试+变异 | 变异使行为红；无装饰断言 |

## 分批
M1 schema+manifest+硬失败 → M2 重复收敛/别名 → M3 默认等价比对+launch hash → M4 回滚演练/门禁接入。
