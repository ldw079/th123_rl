# Decision Log（R17-5/R17-12）

> 格式：日期 | 决策 | 证据/哈希 | owner | 状态。每次窗/架构决策一行。

| 日期 | 决策 | 证据/哈希 | owner | 状态 |
|---|---|---|---|---|
| 2026-10-25 | 监督 P0 修复：停滞看门狗 kill 后必须 spawn；boot/死亡/停滞统一 `_spawn_learner_proc` | commit `0c4bec1`；`tests/test_fleet_watchdog_restart_v1.py` 7项；门禁 740/0/0 `D:\temp\gate_supervisor_fix.txt`；窗口日志 `D:\temp\supervisor_fix_window_20261025.log`（停 23:30:02→全启 23:31:08；live kill 26588→24980 7.3s；新 supervisor PID 6852；alert 已清） | construction | 已部署/验收 |
| 2026-10-25 | postmortem 追加 suika 第二例（同根因再次发生；旧 supervisor 未修时的证据） | commit `01316f4`；`docs/_audit/incidents/incident_20261025_learner_stall.md` 附节 | construction | 已归档 |
| 2026-10-25 | R17 制度 12 条 + 方法论复盘 + 空间只读地图 + UKEMI 窗预注册 | commit `d690faf`；`METHODOLOGY.md` §0 R17；`PARALLEL_WORKFLOW.md` §R17；`docs/_audit/methodology_retro_20261026.md`；`docs/_plans/window_ukemi_20261026_prereg.md` | construction | 待 auditor 复核 |
| 2026-10-25 | BC 锚 P0 修复（标签泄漏/独立真值/严格判据/原子部署）+ W4 slot registry 设计 | commit `3279038`/`0c4bec1`；`docs/_audit/bc_anchor_p0_fix_20261026.md`；`docs/_plans/slot_registry_migration_20261026.md` | construction | 待 auditor 复审 |
| 2026-10-26 00:43 | P0 主臂全灭（fleet wipe）：恢复+根因=23:30 窗用 Start-Process 启动 fleet 成为工具后台作业子孙，00:43:07 回合结束 harness 清后台作业进程树 kill 级联 | 事故 docs/_audit/incidents/incident_20261026_fleet_wipe.md；恢复 01:13:41 WMI bat（supervisor 26012/learners 3208/19572/23072/actors 19924/24644/35448）；control 25372/9856 存活；hb 恢复 01:16:14 | construction | 已恢复；预防待落地（WMI launch helper/UKEMI 脚本改 WMI）；R17-12 重开 |
