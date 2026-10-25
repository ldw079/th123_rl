# 窗口预注册（R17-1）：2026-10-26 UKEMI env-only

> 依据：R17 预注册单；单变量窗；冻结评估夹具；行为指标（Behavior Metrics Registry）。
> 目标：验证 `TH123_BUFFER_UKEMI_DIR=1` 对"受身/起身方向"行为的影响（用户观察：逃压/起身主动性）。

## 窗名/日期/责任人
- 窗名：UKEMI_DIR env-only（v9）
- 日期：2026-10-26 10:30（预计 ≤10min，含重启）
- 责任人：construction（执行）；auditor（评估）；Lead（批准）

## 假设（可证伪）
- H1：`TH123_BUFFER_UKEMI_DIR=1`（当前部署 0）启用受身方向缓冲后，被压/倒地后 20F 内
  **方向逃离/受身选择率↑**，且不增加被击/空挥。
- 证伪：若 UKEMI 事件后移动占比无变化或 KL/ent 退化，则假设不成立（回滚 env=0）。

## 单变量
- 仅改 `TH123_BUFFER_UKEMI_DIR`（0→1）；其它 env 不变；无代码改动。

## 指标 + 门限（初）
| 指标 | 定义/来源 | 门限 |
|---|---|---|
| 受身后 20F 移动/受身选择率 | frame logs/bh 事件 | ↑≥5% 相对 |
| 被压后 20F 逃压动作占比 | 同上 | 不降 |
| 空挥/被击 | 奖励成分/帧 | 不恶化 |
| KL/ent | learner 日志 | KL≤0.30、ent 不退化 |
| combo 选择率 | macro_counts | 不降 |

## 样本量/观察期
- 最少 30min（≥2 批新 episode/角色）；建议 60min 初判、2h 复核。
- 作废段：marisa 21:57-23:15、suika 23:07-23:28、23:30-23:31 重启段（auditor 标注）。

## 停止规则
- 达标：指标门限满足 60min → 保留；
- 不达标：60min 未见方向改善 → env 回滚 0（记录）；
- 异常：hb 不新鲜/ALERT/游戏数<4/learner 缺员 → 立即回滚并告警。

## 回滚步骤（演练过）
1. `TH123_BUFFER_UKEMI_DIR=0`（bat/env）→ 停止 main → 重启 supervisor（新代码）→ 验证
   3 learner/3 actor/4 游戏/control；预期 ≤2min。
2. 失败：回滚 env + 旧 supervisor 代码（`git show 0c4bec1^:fleet_supervisor.py`）。

## DoD（用户观察→指标映射）
- "逃压/受身更主动"→ 受身后移动/受身选择率↑、被压损失不增；
- "没变差"→ 空挥/KL/ent/combo 选择率不退化；
- 数据/日志：窗前后各 60min 对比（冻结夹具：同角色/对手池/种子/局面集）。

## 备注
- 与 task-58 执行器修复、BC 锚部署窗（若批准）解耦；不同窗口不叠加变量。
