# Decision Log（R17-5/R17-12）

> 格式：日期 | 决策 | 证据/哈希 | owner | 状态。每次窗/架构决策一行。

| 日期 | 决策 | 证据/哈希 | owner | 状态 |
|---|---|---|---|---|
| 2026-10-25 | 监督 P0 修复：停滞看门狗 kill 后必须 spawn；boot/死亡/停滞统一 `_spawn_learner_proc` | commit `0c4bec1`；`tests/test_fleet_watchdog_restart_v1.py` 7项；门禁 740/0/0 `D:\temp\gate_supervisor_fix.txt`；窗口日志 `D:\temp\supervisor_fix_window_20261025.log`（停 23:30:02→全启 23:31:08；live kill 26588→24980 7.3s；新 supervisor PID 6852；alert 已清） | construction | 已部署/验收 |
| 2026-10-25 | postmortem 追加 suika 第二例（同根因再次发生；旧 supervisor 未修时的证据） | commit `01316f4`；`docs/_audit/incidents/incident_20261025_learner_stall.md` 附节 | construction | 已归档 |
| 2026-10-25 | R17 制度 12 条 + 方法论复盘 + 空间只读地图 + UKEMI 窗预注册 | commit `d690faf`；`METHODOLOGY.md` §0 R17；`PARALLEL_WORKFLOW.md` §R17；`docs/_audit/methodology_retro_20261026.md`；`docs/_plans/window_ukemi_20261026_prereg.md` | construction | 待 auditor 复核 |
| 2026-10-25 | BC 锚 P0 修复（标签泄漏/独立真值/严格判据/原子部署）+ W4 slot registry 设计 | commit `3279038`/`0c4bec1`；`docs/_audit/bc_anchor_p0_fix_20261026.md`；`docs/_plans/slot_registry_migration_20261026.md` | construction | 待 auditor 复审 |
| 2026-10-26 00:43 | P0 主臂全灭（fleet wipe）：恢复+根因=23:30 窗用 Start-Process 启动 fleet 成为工具后台作业子孙，00:43:07 回合结束 harness 清后台作业进程树 kill 级联 | 事故 docs/_audit/incidents/incident_20261026_fleet_wipe.md；恢复 01:13:41 WMI bat（supervisor 26012/learners 3208/19572/23072/actors 19924/24644/35448）；control 25372/9856 存活；hb 恢复 01:16:14 | construction | 已恢复；预防待落地（WMI launch helper/UKEMI 脚本改 WMI）；R17-12 重开 |
| 2026-10-26 01:40 | 3 项预防补齐：WMI 唯一启动入口（detached+父链检查）/ 心跳进程数+max_log_age+缺员告警写入清除 / 父杀存活行为测试 / 窗口脚本禁 Start-Process（静态辅助+行为证据） | commit 1afbfba；门禁 **743 PASS / 0 WARN / 0 FAIL**（D:\temp\gate_fleet_prevention2.txt）；测试：detach+父杀 9 项、heartbeat health 10 项、window policy 1 项；health probe --check PASS；旧窗脚本归档 .archive | construction | 代码已就绪，15:00 加固窗部署 |
| 2026-10-26 02:35 | 外部看门狗 v2（AR-1..9）：fleet_lock 租约锁/stale 接管、fleet_health 自动恢复(必需集排除 control/连续2次/限流1/10min/失败退避/二次锁+二次快照/单实例/告警去重)、WMI detached、无 kill；15:00 加固窗部署+AR-9 现场 | commit 本批；门禁 **744 PASS/0/0**（D:\temp\gate_ar_final.txt）；	ests/test_fleet_auto_recovery_v1.py 16 项（含真实 subprocess dummy fleet）；docs/_plans/fleet_autorecover_impl_20261026.md；15:00 窗脚本 D:\temp\hardening_window.ps1 | construction | 代码+测试就绪；未部署；15:00 部署/验收 |
| 2026-10-26 02:55 | AR-2 增量（stale 锁 fleet_alert/CAS 原子创建/ttl 7200/owner 释放/窗 acquire 失败 abort） + AR-6（仅 sup 死→锁+孤儿 PID 二次校验清理+WMI 整队+复核；sup 活≥2 缺不整队） | commit 本批；门禁 744/0/0（`D:\temp\gate_ar6.txt`）；测试 34 项（AR-1..8 含真实 dummy 孤儿场景）；`docs/_plans/fleet_autorecover_impl_20261026.md` §5；窗脚本 rc/abort/ttl/owner 已改 | construction | 代码+测试就绪；15:00 部署/AR-9 现场 |
| 2026-10-26 03:50 | P1 停滞阈值：learner=max(env, BATCH_WAIT_MAX+120)，bat 显式 `TH123_WATCHDOG_STALL_LEARNER_S=600`；stall 重启次数入 heartbeat.health；hardening 窗 stall 演练 suspend 620s | commit 本批；门禁 744/0/0（`D:\temp\gate_stall_p1.txt`）；`tests/test_fleet_watchdog_restart_v1.py` 11 项（动态阈值/actor 300） | construction | 代码+env 就绪；15:00 部署验收 |
