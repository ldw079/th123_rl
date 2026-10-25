# 自动恢复 watcher 设计审计（R17-12 扩展；2026-10-26 02:2x 设计阶段）
> **状态**：设计审计，只读；截至 02:2x 未在仓库/D:\temp 找到 watcher/autorecover/maintenance.lock 实现与测试（`git log` 最新 f9cd46e 未含），本审计针对 Lead 02:22 设计文本。
> **结论**：方向正确、可实施；**设计缺少 stale-lock/TTL、锁强制入口、watcher 自身 WMI 启动、边界精确定义与行为测试**，补齐前不通过；15:00 部署前须给实现+测试+现场证据。R17-12 继续冻结。

## 1. 设计摘要（Lead 02:22）
- 触发：关键缺员（supervisor 缺 / ≥2 必需进程缺）连续 2 检查 → WMI 恢复（限 1 次/10min、不 kill、写 recovery 记录/日志/alert）。
- 维护锁：`STORE/fleet_maintenance.lock`；窗脚本/手工停启写锁，恢复后删；watcher 见锁不恢复。
- 目的：自动恢复全灭/缺员，同时防 UKEMI/BC/演练窗被误重启。

## 2. 审计判定与缺口
| 要点 | 设计判定 | 缺口/必须补充 |
|---|---|---|
| ① 触发条件（防误判） | **条件通过** | 需精确定义"必需进程"（sup + 3 learner + 3 main actor + 4 games；**排除 control**）、检查间隔、连续 2 次的时间窗、"supervisor 缺"与"supervisor 在但 ≥2 子进程缺"分支；单进程缺/短抖动不得触发（由 supervisor 自身重启负责）；需 heartbeat age 辅助；窗/维护锁期间抑制 |
| ② 维护锁双向语义 | **P1 缺口（stale-lock）** | 未定义锁内容（owner/pid/reason/时间/过期/租约）、原子创建、**stale lock 超时/告警/接管**；若窗崩溃留锁→watcher 永久不恢复；锁必须在停进程**前**写、健康 PASS 后删；watcher 检测到缺员后需**二次确认锁**再动作；手工停启必须走统一 helper，不能各写各的 |
| ③ 限流/不 kill 证明 | **条件通过** | 限 1 次/10min；必须证明 watcher 路径**无 taskkill/Stop-Process**（只 WMI Create）；失败重试退避/告警节流；recovery record 必须落盘（时间/触发/动作/结果/是否被锁抑制） |
| ④ 行为测试（R15） | **FAIL（未提供）** | 需真实 subprocess dummy fleet：缺 1 不触发/缺 2 触发；连续 2 检查；锁抑制；stale 锁处理；限流；失败告警不轰炸；**无 kill 断言**（记录/监控 watcher 调用）；恢复后健康；不能纯串断言 |
| ⑤ 恢复失败告警不轰炸 | **条件通过** | 告警去重/退避（如每次尝试一条、10min 窗口最多 N 条）；恢复失败后不得循环 spawn；alert 恢复后清除/记录 |
| ⑥ 与 supervisor 职责边界 | **P1 缺口** | 明确"单进程缺→supervisor 重启；supervisor 缺/≥2 关键缺→watcher"；watcher 启动前检查**单实例**与 supervisor 是否已恢复（race），避免双重重启/重复 fleet；watcher 也须 **WMI detached 启动**（不能重蹈 Start-Process 全灭） |
| ⑦ 部署/窗集成 | **条件通过** | 15:00 加固窗部署 watcher；UKEMI/BC/演练脚本统一写锁/释放；窗后校验父链/锁/无重复 watcher；回滚路径 |

## 3. 设计验收判据（供 15:00 窗）
| ID | 判据 | 证据 |
|---|---|---|
| AR-1 | 触发阈值：单缺/抖动不触发，连续 2 检查+关键缺触发 | 真实进程测试/日志时间戳 |
| AR-2 | 维护锁：窗/manual 写锁→watcher 抑制；健康后删；stale-lock TTL/告警/接管可复现 | 锁文件内容/时序/测试 |
| AR-3 | 限流：1/10min；恢复记录完整；失败不循环 | recovery 记录/日志 |
| AR-4 | 不 kill：watcher 路径无 taskkill/Stop-Process（代码审查+运行时审计/测试） | 代码/测试/调用记录 |
| AR-5 | 告警：失败/恢复各一条（去重/退避），恢复清除 | alert 文件/日志 |
| AR-6 | 边界：单缺由 supervisor 处理；watcher 不双启；单实例检查 | 并发场景测试 |
| AR-7 | watcher 自身 WMI detached（父=gone/WmiPrvSE），非工具作业子孙 | 父链检查 |
| AR-8 | R15 行为测试全绿（dummy fleet 真实 subprocess；变异使红） | 测试输出 |
| AR-9 | 15:00 现场：停 supervisor→watcher 恢复；锁抑制；失败告警；health PASS | 窗日志/证据包 |

## 4. 结论
- **设计方向通过；实现前需补**：stale-lock/TTL/租约、统一锁 helper、watcher WMI 启动、边界精确定义、R15 行为测试、恢复记录/告警节流。
- 15:00 部署前给实现+测试；窗后我按 AR-1..9 核验，通过才纳入 R17-12②③。W4 继续冻结。

## 5. 实现核验（commit `53d7e32`；2026-10-26 02:4x）
| AR | 判定 | 证据/缺口 |
|---|---|---|
| AR-1 触发 | **PASS** | 关键连续2检查触发；单 learner 缺→alert_only；`--auto-recover` 未开不恢复（测试） |
| AR-2 维护锁 | **条件 PASS（4 缺口）** | 锁字段/TTL=1800/stale 可接管测试 PASS；**stale 无 alert 文件**（仅 log/acts）、**acquire 非原子 CAS**、**TTL 无续约/窗>30min 风险**、`--unlock` force 可清任意 owner |
| AR-3 限流/退避 | **PASS** | 1/10min、失败退避、recovery 记录测试 |
| AR-4 无 kill | **PASS** | 源码无 taskkill/Stop-Process；恢复仅 snapshot+WMI launch；测试 |
| AR-5 告警 | **PASS** | 相同 bad 集合去重、恢复清除 |
| AR-6 单实例/边界 | **PASS（单实例）/ PENDING（边界）** | 单实例测试；**仅 sup 死而子进程活**场景未测，watcher 整队恢复可能重复/端口冲突 |
| AR-7 watcher detached | **PENDING 15:00** | `--parent-check` 已有；现场需 watcher 父链=gone/WmiPrvSE |
| AR-8 R15 测试 | **PASS** | 真实 dummy fleet：17 PASS/0（Lead 记录16，实测17）；含杀1 learner不触发/杀sup触发 |
| AR-9 现场 | **PENDING 15:00** | `hardening_window.ps1` 已含 AR-9a/9b/stall；待执行日志 |

- 门禁 `D:\temp\gate_ar_final.txt` **744/0/0**；`test_fleet_auto_recovery_v1.py` 17/0；health probe PASS；UKEMI 脚本停前写锁/健康后 unlock；旧窗脚本已归档。
- **15:00 前需补**：stale alert；锁原子 acquire/续约；`--unlock` owner 校验；hardening 窗停前写锁；**仅 sup 死场景真实恢复/无重复验证**；decision log 条目 typo（"16项" vs 实际17）。
- 结论：测试层 **AR-1/3/4/5/6(单实例)/8 PASS；AR-2 条件 PASS；AR-6 边界/AR-7/9 PENDING**；15:00 按 AR-1..9 正式判定，W4 冻结。

## 6. AR-6 修订设计审计（Lead 02:47：仅 sup 死→清孤立子进程→WMI 整队）
**新增风险/必须定义**
1) **AR-4 语义变更**：watcher 从"无 kill"变为"只清理已验证 main 孤立子进程的精确 PID"；必须更新 AR-4 证据：禁 kill-by-name、仅 PID+路径+命令行+父链校验、**control 绝不触碰**、孤儿清单与新旧 PID 记录；测试需真实进程，变异（放宽清单/按名杀）必须红。
2) **恢复锁与窗锁双向语义**：watcher 恢复期间 acquire 维护锁→窗脚本 acquire 会失败；但当前 UKEMI 等脚本把 `--lock` 输出 `Out-Null` 且**不检查返回码，失败仍继续停进程** → 窗可能在 watcher 恢复中停队/双杀。必须：窗 `--lock` 失败即 abort；watcher 恢复只在无有效锁时进行；恢复锁 crash 后 TTL/finally release；记录 lock owner。
3) **sup 存活但 ≥2 必需进程缺**：设计仍会 WMI 启整队 → 可能与存活 supervisor/子进程重复/端口冲突。必须定义分支：sup 存活时不整队 launch（只告警/由 supervisor 自身恢复；或仅补缺失并校验单实例），并加测试。
4) **孤儿清理竞态**：snapshot 后 supervisor 可能已被 supervisor 自身路径恢复/新进程出现；清理前需二次快照+PID 存活+命令行校验；不得清理 control/新 supervisor/新子进程；清理失败不 launch 或告警。
5) **锁 TTL**：窗 acquire 显式 ttl=7200 或续约；恢复锁与维护锁不得互相覆盖；`--unlock` owner/pid 校验。
**15:00 必测场景（补充）**
- 仅 sup 死、子进程存活：恢复后无重复 learner/actor/game、端口无冲突、control 未动；
- sup 存活、≥2 子进程缺：不得重复 supervisor/整队；行为明确；
- 窗锁有效时停 supervisor：watcher 抑制；窗 `--lock` 失败必须 abort；
- 恢复锁 crash/TTL 后不永久锁死；stale 告警；
- 无 kill-by-name；仅孤儿 PID 清理；变异红。
**AR-6 判定**：设计方向可接受，但上述 1–4 不定义/不测试前 **AR-6 不能 PASS**；15:00 按场景证据正式判定。
