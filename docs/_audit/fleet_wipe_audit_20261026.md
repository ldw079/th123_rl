# 主臂全灭事故审计（P0；R17-12 重开；2026-10-26 01:2x 初版）
> **基线**：HEAD `5a49087`；只读，不恢复/不改训练。证据包原始文件：`D:\temp\_audit51_maindeath_evidence_A.txt` / `_events.txt` / `_events2.txt` / `_events3.txt` / `_process_audit.txt` / `_construction.txt`。
> **结论**：根因证据链 **PASS（收敛）**；预防落地 **部分 FAIL**；R17-12 新四条件 ①PASS ②FAIL ③④pending；W4/迁移继续冻结。

## 1. 事实/时间线（实证）
| 时刻 | 事实 | 证据 |
|---|---|---|
| 00:31:28 | supervisor console 最后一行（league 重算） | `fleet_supervisor_console_restart.log` |
| 00:41:26 | `watchdog_rejects.log` 最后写入 | 文件 mtime |
| 00:41:59 | 施工健康检查 hb 2s、无 alert、3 learner/3 actor/4 games | 施工输出（postmortem §1） |
| 00:42:58 | BC anchor v3 merge **dry-run**（只读） | `D:\temp\scratch\bc_anchor_v3_merge_dryrun.txt` |
| 00:43:01 | `fleet_heartbeat` 最后写入 | hb mtime |
| 00:43:04 | `fleet_heartbeat.wd` 最后写入 | wd mtime |
| 00:43:07 | 施工回合结束（git commit/push） | postmortem/git |
| **00:43:10-11** | **主 supervisor/3 learner/3 actor/主游戏全部消失** | actor 日志停更；进程表全无 |
| 01:13:16 | Lead 报 P0（仅 control 存活、hb 30min stale） | Lead 消息 |
| 01:13:41 | WMI 启动 `cmd /c train_batch_launch.bat`（ret=0） | postmortem/恢复日志 |
| 01:15:12 | 全启 supervisor26012/learners3208,19572,23072/actors19924,24644,35448/games21000,21010,21020,21080 | postmortem/进程表 |
| 01:16:14 | hb 恢复 age 4s、无 alert | 实测/postmortem |

- **监护事实**：console `.err` **0B**、`.log` 无 Traceback/退出码；Application 无 python/1000/1001/1026 错误；System 无 Kernel-Power/41/42/107/109/506/507/6008 关机/电源事件；Security 4688/4689 **审计关闭**、无 Sysmon → 无直接 kill 事件。
- **对照**：control learner25372/actor9856（WMI 启动，父 gone）**全程存活**；主臂 6 进程+3 游戏同时死 → 选择性进程树清理，非 OS 级/全局。

## 2. 根因（收敛证据链，非直接杀进程取证）
**直接原因**：23:30 监督修复窗脚本 `D:\temp\supervisor_fix_window.ps1:26` 用 **`Start-Process`** 启动 supervisor → fleet 成为 **工具 shell/后台作业的子孙**；施工 00:43:07 回合结束时 harness 清理后台作业，进程树 kill 级联至 fleet（00:43:10-11）。
**支持证据**：
1) 旧窗脚本确实含 `Start-Process`（第26行）启动 supervisor；其 learners/actors/games 均为 supervisor 子孙。
2) 00:43:07 回合结束→00:43:10 全灭，时序吻合。
3) console 无 Traceback/退出码、无 OS 电源/关机事件 → 非自身异常/OS 关机。
4) control（WMI 启动，父 WmiPrvSE→gone）存活 → 排除全局 OS kill；恢复用 WMI 后 parent=gone、结构免疫。
5) 施工 00:37/00:38 的 kill-by-name 仅清 th123 端口且发生在 5min 前（当时 hb 仍 2s），非直接因。
**取证局限**：无 4688/Sysmon/进程审计，无法给出 `taskkill/作业清理` 的直接事件记录；结论为"脚本启动方式+时序+对照存活+无异常"的强收敛推断。建议启用进程审计（4688 或 Sysmon）与父链日志。

## 3. 预防落地核验
| 项 | 判定 | 证据/缺口 |
|---|---|---|
| WMI 唯一入口 `tools/fleet_launch_wmi.py` | **PASS** | Win32_Process.Create + `--check` 父链；当前 `--check` PASS（supervisor26012 parent=gone） |
| 窗脚本全改 WMI | **FAIL（P1）** | `ukemi_window.ps1` 已 WMI；**旧 `supervisor_fix_window.ps1:26` 仍 Start-Process**，未归档/转换/门禁 |
| 禁止 kill-by-name | **PASS（检查）/无强制** | 活跃代码无 `taskkill /IM`/Stop-Process -Name；仅 `_archive/legacy_20261006/cleanup_r13.py` 旧脚本；缺静态门禁 |
| 心跳进程数/log age 告警 | **FAIL（P1）** | `write_heartbeat` 仅 timestamp/alert；`write_watchdog_status` 仅 cpu/n_rej/machine/aux；**无 learner/actor 计数、max log age、缺员告警**（postmortem §4.4 TODO） |
| 父杀→fleet 存活行为测试（R15） | **FAIL（P1）** | 仅有 `test_fleet_watchdog_restart_v1`（停滞重启）与 `test_detach_v1`（WMI 回退逻辑）；无真实 subprocess 父杀存活测试 |
| 恢复后健康 | **PASS** | gate `PASS 19/0/0`；supervisor parent=gone；3 learner+3 actor+control 齐；hb fresh；无 alert |

## 4. Postmortem/Decision Log
- `docs/_audit/incidents/incident_20261026_fleet_wipe.md`：**内容 PASS**（时间线/根因/排除项/恢复/预防/影响）。
- `docs/_audit/decisions/decision_log_20261026.md`：00:43 条目含事故/恢复/证据，状态"已恢复；预防待落地"（**与 §3 FAIL 一致，未虚报闭环**）。
- commit `5a49087` 已含 postmortem+decision log+WMI helper；"push 0/0" 不影响本地证据可审。

## 5. R17-12 新四条件
| 条件 | 状态 |
|---|---|
| ① 全灭事故 postmortem+证据 | **PASS** |
| ② 预防落地证据（WMI+父链+告警测试） | **FAIL（§3 三项未落地）** |
| ③ 停滞演练通过（重排 15:30/明早） | **pending** |
| ④ 无新增 P0 24h | **pending** |
→ **W4/迁移继续冻结**；②补齐+③④通过后才可关闭。

## 6. 建议（09:30 前）
1) 归档/改造 `supervisor_fix_window.ps1` 为 WMI；加入门禁：任何 fleet/window 启动路径禁止 `Start-Process`（源码/行为检查）。
2) 心跳扩展：learner/actor 计数、max log age、supervisor PID；缺员>120s 机器告警；写消费方/测试（R15，行为测试真进程）。
3) 新增父杀存活行为测试：启动 dummy fleet（父 Popen）→ 杀父→子 fleet 仍活/被 WMI 接管；变异（恢复 Start-Process）使测试红。
4) 静态门禁禁 kill-by-name（仅精确 PID/父链/端口+父核对）。
5) 建议启用 4688/Sysmon 或 supervisor 父链/进程数审计（非阻塞但下次取证关键）。
6) 15:30 停滞演练后复核 R17-12 ①–④ 并更新 postmortem/decision log 状态。

## 7. 预防复验（commit `1afbfba`；2026-10-26 01:4x）
| 项 | 判定 | 证据 |
|---|---|---|
| 旧窗脚本归档 | **PASS** | `supervisor_fix_window.ps1` → `.archive`（非 .ps1 不可执行） |
| 窗口脚本 WMI/静态门禁 | **PASS** | `test_window_launch_policy_v1.py` 1/0；`ukemi_window.ps1` 启动段 WMI；`D:\temp\*.ps1` 无 Start-Process+fleet |
| WMI 唯一入口/父链 | **PASS** | `fleet_launch_wmi.py --check` → supervisor26012 parent=gone |
| 心跳扩展（代码/测试） | **PASS（代码）** | `test_fleet_heartbeat_health_v1.py` 10/0：`.health` 字段/缺员→`.fleet_alert`/恢复清除/`wd.health` 5字段兼容/health_now |
| 心跳扩展（运行时） | **PENDING 15:00** | 当前 supervisor 为 01:13 旧代码，`fleet_heartbeat.health`/`.fleet_alert`/`.wd.health` 尚未生成；部署后须重验 |
| 父杀存活行为测试 | **PASS** | `test_fleet_detach_health_v1.py` 9/0：WMI 子父=WmiPrvSE；杀 PowerShell 启动器后子进程仍存活；按 PID 清理（非 kill-by-name） |
| 外部健康探针 | **PASS** | `fleet_health.py --check`：sup1/learners3/actors3/ctl2/games4/hb 32s |
| 门禁 | **PASS** | `gate_fleet_prevention2.txt` **743 PASS / 0 WARN / 0 FAIL** |
| Decision Log 更新 | **PASS（70b2961）** | 已补 01:40 条目：commit 1afbfba/743/0/0/测试 9+10+1/health probe PASS/旧脚本归档；状态=代码已就绪，15:00 部署 |
| Postmortem 预防证据 | **PASS（内容）** | §6 表已补（含“未部署”标注）；部署后需更新状态 |

**结论**：预防 **代码/测试/门禁/Decision Log PASS**；**运行时心跳文件/告警待 15:00 部署**；R17-12 ② 仍为**条件 PASS**，W4 冻结。
