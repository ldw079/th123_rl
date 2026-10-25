# 外部看门狗自动恢复实现说明（AR-1..9 映射；2026-10-26 02:35）

> 对应 Lead 02:22/02:25 与 auditor `docs/_audit/fleet_autorecover_design_audit_20261026.md`。
> 状态：**代码+测试完成，未部署**；15:00 加固窗部署+现场验收（AR-9）。
> 门禁：744 PASS / 0 WARN / 0 FAIL；测试 `tests/test_fleet_auto_recovery_v1.py` 16 项。

## 1. 组件
- `tools/fleet_lock.py`：统一维护锁（租约 owner/pid/reason/created/expires；**原子 tmp+rename**；
  stale TTL 超时→告警+可接管；`--acquire/--release/--status/--owner-ok`）。
- `tools/fleet_health.py`：
  - `--check`/`--loop N --auto-recover`/`--status`/`--parent-check`/`--lock/--unlock/--clear`
  - 必需集合 = sup + 3 main learner + 3 main actor + 4 games（**排除 control**）；
  - 单实例 `fleet_watcher.lock`（pid 存活检查）；
  - 恢复：WMI `fleet_launch_wmi.launch()`（detached），**无 kill**；
  - recovery 记录：`fleet_recovery.json/.log` + `fleet_heartbeat.recovery`；
  - 告警去重（bad 集合变化才重写）；恢复后 health 复核与清除。
- `tools/fleet_launch_wmi.py`：WMI 唯一入口（`train_batch_launch.bat`）。
- 窗脚本 (`D:\temp\ukemi_window.ps1`/`hardening_window.ps1`)：停进程**前**写锁、健康 PASS 后删；
  启动用 WMI；失败 exit 前 unlock。

## 2. AR 映射
| AR | 实现 | 证据 |
|---|---|---|
| AR-1 触发阈值 | 单 learner/actor 缺→仅告警（supervisor 自身恢复）；sup 缺或必需缺失≥2→关键；连续 2 检查且间隔≥120s | 测试 `AR-1`：关键连续触发；单 learner 缺→alert_only |
| AR-2 维护锁 | 租约锁原子创建；有效锁抑制恢复；stale 锁告警+可接管；健康后窗脚本删 | 测试 `AR-2`：有效锁→maintenance；stale→stale_lock_takeover+recover |
| AR-3 限流/退避 | 1 次/10min；失败记录；30min 内 ≥3 失败→backoff 只告警；恢复记录完整 | 测试 `AR-3`：rate_limited / backoff |
| AR-4 不 kill | watcher 源码无 `taskkill`/`Stop-Process`；恢复路径只 snapshot+launch | 测试 `AR-4` 静态+行为；代码审查 |
| AR-5 告警 | bad 集合去重；恢复后清除；失败一次一条（不轰炸） | 测试 `AR-5` |
| AR-6 边界/单实例 | 单缺→supervisor；watcher 单实例锁；恢复前二次确认锁+二次快照(race) | 测试 `AR-6`；`loop_tick` race 分支 |
| AR-7 watcher detached | WMI 启动；`--parent-check` 输出父链证据 | 15:00 现场采集（脚本内） |
| AR-8 R15 行为测试 | 真实 subprocess dummy fleet（1 sup+3 learner+3 actor）：全在位 PASS/杀 1 learner 不触发/杀 sup 触发 | 测试 `AR-8` 16 项全绿 |
| AR-9 现场 | 加固窗：停 supervisor→watcher 恢复；锁抑制；stall 演练；health PASS | `D:\temp\hardening_window_20261026.log`（15:00 生成） |

## 3. 15:00 加固窗步骤（`D:\temp\hardening_window.ps1`）
1. 记 HEAD；PID 方式清旧 watcher；停 main→WMI 启动 bat；
2. 验收 3 learner/3 actor/4 游戏/detached/心跳 `.health` `.wd.health`；
3. 锁状态演示（acquire/status/release）；
4. WMI 启动 watcher `--loop 60 --auto-recover`，记 pid/parent；
5. **AR-9a**：停 supervisor(仅该 PID)→watcher 应 WMI 恢复新 supervisor（≤4min）；
6. **stall 演练**：suspend marisa learner>300s→supervisor kill+spawn（≤10s 目标）；
7. 复核 health/`fleet_alert` 清除、watcher parent-check；
8. postmortem 状态→"已部署并验收"；auditor 按 AR-1..9 核验。

## 4. 反债评估（R16）
- 唯一锁实现（fleet_lock）+ 唯一启动入口（WMI），窗/手工/看门狗共用，避免各自实现；
- 恢复仅 WMI spawn，无 kill 与无 shell 子孙（根除 00:43 事故模式）；
- watcher 单实例+租约锁防双 watcher/永久锁；退避防重启风暴；
- 过渡：`--auto-recover` 默认关闭，15:00 起显式开启；窗口脚本用锁避免误恢复。
