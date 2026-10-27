# 窗口预注册（R17-1）：2026-10-27 UKEMI env-only（修订版，10:30 开）

> 依据：R17 预注册单 + auditor 10:0x 判 FAIL 修订要求。
> **状态：auditor 13:10 前复核列签 → Lead 13:30 批 → 2026-10-28 10:30 执行（70min）。**
> 单变量窗；冻结评估夹具；行为指标（Behavior Metrics Registry）；维护锁+WMI+回滚。

## 窗名/日期/责任人
- 窗名：UKEMI_DIR env-only（v9）
- **开始：2026-10-28 10:30**（固定窗 **70min**，至 11:40；含 ≤2min 重启）
- 责任人：construction（执行）；auditor（指标核验/独立真值）；Lead（批准/窗口拍板）

## 假设（可证伪）
- H1：`TH123_BUFFER_UKEMI_DIR=1`（当前 0）使受身/起身方向决策更主动：
  **dir_f/dir_b 每千决策↑**、受身/防御决策占比变化符合预期、且不劣化 skip/exec/reg/ent/KL。
- 证伪：70min 固定窗内指标未达门限 → 回滚 env=0（记录）。

## 单变量
- 仅 `TH123_BUFFER_UKEMI_DIR` 0→1（bat）；无代码改动、无其它 env 变化。

## 指标（精确定义/分母）
| 指标 | 定义 | 分母 | 门限 |
|---|---|---|---|
| dir_f/dir_b 每千决策 | 前进/后退方向决策数 / 决策数 ×1000 | 决策（decisions） | 相对窗前提**升**（至少一项↑、另一项不显著恶化） |
| 受身/防御决策占比 | 受身（UKEMI/tech）决策数/**受身机会数**；防御决策/决策 | 受身机会=被击倒/受身窗口次数（定义见下） | 报告+不劣化（受身↑优先） |
| 基线 | 窗起时记录 dir_f/dir_b 基线值（UKEMI_DIR=0 下的当前值）+ 基线快照 hash | 窗起 70min | 记录 |
| skip% | 被跳过的决策 / 决策 | 决策 | **<10%** |
| exec/reg | 执行器成功/发起占比 | 发起 | **>0.7** |
| ent | 策略熵（learner 日志） | 每批 | **≥0.75** 均值 |
| KL | \|KL\| 读数均值 | 每批 | **≤0.30** |
| 游戏/进程 | 4 游戏（**exact: 3 main + control 1**）、3 learner/3 actor/control/watcher | 实时 | 缺员=停窗 |

## 样本门（固定窗 70min；auditor 方案 1）
- **每角色 ≥1200 决策**（**stretch 3000，仅记录**）；
- **≥2 帧档**（70min 内可达；"帧档"=frame log 抽样文件，约 30min/档；
  若不足按 episode 档替代并记录）；
- **UKEMI/受身事件门**：每角色 **≥25 次受身机会/事件**（不足则标"事件稀疏"：不判 UKEMI 专项指标，但仍报 skip/ent/KL，不直接判失败）。
- 不足→判"样本门未过"，不判定效果（可延长一次，最多 +30min，需 Lead 批）。
- 作废段：重启/维护锁期间数据剔除；auditor 按时间标注。

## 冻结评估夹具
- 角色：reimu/marisa/suika；对手池：当前 league20+COM 快照（记录版本/哈希）；
- 种子：actor 种子按 (actor,version)；局面集：固定开局距离/天气/卡组清单（记录）；
- 评估脚本版本：`tools/fleet_health.py`/metrics 采集脚本版本 + 窗起止时间；
- 窗前后各 **70min** 用同夹具对比（窗后数据可延后采集，但须同夹具）。

## 停止规则
- **P0/回滚触发器**：进程缺员（learner/actor/game）、hb 停更>120s、crash、alert 无法闭环
  → 立即回滚 env=0 + 单次重启；**ent<0.6 或 KL>0.5 持续 10min** → 回滚。
- 达标：70min 指标门限满足 → 保留 env=1（进入 24h 观察）。
- 不达标：回滚 env=0、记录（不叠加其它变量）。

## 维护锁/WMI/回滚
- 窗脚本 `D:\temp\ukemi_window.ps1`：**先 acquire 维护锁（ttl 7200，失败 abort）** → 停 main（PID/父链）
  → **WMI** 启动 `train_batch_launch.bat`（detached 校验）→ 健康 PASS → 写/删 env → 窗结束删锁；
  watcher 见锁不恢复（现场记录 maintenance 抑制）。
- 回滚：bat `TH123_BUFFER_UKEMI_DIR=0` + 单次重启（≤2min）；失败升级 Lead。
- 证据：`D:\temp\ukemi_window_20261026.log`、health/heartbeat、指标 CSV、auditor 复核记录。

## DoD（可量化）
- 窗脚本执行成功 + 维护锁行为 PASS + WMI detached PASS；
- 4 游戏/3 learner/3 actor/control/watcher 在位、hb fresh、无 alert；
- 70min 样本门满足 & 指标表全部记录 & 门限判定明确（达标/回滚二选一，有证据）；
- auditor 独立复核签名。

## 受身机会/事件计算口径
- 受身机会：`frame_events`/帧日志中 被击倒(knockdown)/进入受身窗口 的事件计数；
- 受身决策：窗口内 UKEMI/tech 方向/按键决策数；分母=机会数（不足 30 → 事件稀疏标注）。
- frame档：frame log 抽样文件（约 30min/档，窗内≥2）；episode档：每局 npz 文件。

## 基线/快照
- 窗起记录：`dir_f/dir_b` 当前基线（UKEMI_DIR=0）、每角色样本门计数、基线快照 hash（文件哈希）。
- 窗后同夹具对比；基线 hash 写入窗日志。

## 基线/观察
- 窗起用 **v2 baseline 工具**重跑并写完整 JSON+sha256 到窗日志（`window_baseline_ukemi_<ts>.json`（窗起动态时间戳））；
- 窗后 **12:40** 观察（检查点）；作废段/样本门按上。

## 独立真值
- 指标采集脚本与判定由 auditor 用**窗内原始 episode/log**独立复算（不采用施工方自报聚合）；
- 对比窗前后同夹具；随机抽 10 帧档人工核对 dir_f/dir_b 计数口径。
- **窗内 watcher**：`fleet_health.py --loop 60 --auto-recover`（带自动恢复；窗内故障也可按 stop 规则人工回滚；不得无恢复静默）。
- **裁决（Lead 10:24）**：UKEMI 顺延 **2026-10-28 10:30–11:40**（70min）；决策门 **≥1200/char（stretch 3000 仅记录）**；样本不足按稀疏标注；失败 env=0 单次重启；观察 11:45。
