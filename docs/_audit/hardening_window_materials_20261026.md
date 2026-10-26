# 15:00 加固窗材料（2026-10-26；≤35min）

> 顺序：helper live 停 → WMI 部署 → AR-9a → AR-9b → stall 620s → evidence。
> 脚本：`D:\temp\hardening_window.ps1`（v2，parse OK）；日志 `D:\temp\hardening_window_20261026.log`。

## 1. helper 整改（train_stop_clean.py）
- live 停止 main+control+watcher；**先 acquire 维护锁**；写 `train_stopped_clean`+停机账
  （PIDs/时刻/原因）；按 PID/父链（禁 kill-by-name）；测后 WMI 恢复 health PASS；
  测试模式 marker 隔离（真实 dummy；真实 fleet 不被计/杀）；`--live` 硬门（默认拒绝真停）。
- 证据：`tests/test_train_stop_clean_v1.py` 7 项；live 实战记录（本窗）。

## 2. AR 现场
- AR-9a：仅停 supervisor（子进程活）→ watcher AR-6 恢复；核 exact learners3/actors3/games4、
  control 未动、无重复/端口冲突。
- AR-9b：维护锁→停 sup→60s 不恢复；解锁→恢复。
- stall：suspend marisa learner **620s**（阈值 600）→ kill+spawn；`stall_restarts` 递增。
- 证据：`D:\temp\hardening_window_20261026.log`；auditor 按 AR-1..9+AR-6 核。

## 3. powercfg / crash dump / 无自启 / L3
- powercfg：LIDACTION/PBUTTONACTION/STANDBYIDLE/HIBERNATEIDLE/VIDEOIDLE AC=DC=0（窗内逐项展示；
  隐藏项以已执行命令+注册表记录为准）；**不禁 S0**（用户主动关机）。
- crash dump：`tools/crashdump_config.py --check` 记录 CrashControl/pagefile；
  **无法现场触发崩溃→如实记录"未实测"**；DedicatedDumpFile=D:\temp\dedicated.dmp 尝试（非管理员记录）。
- 无自启：`train_resume_on_boot` 标志不存在、schtasks 无 th123 训练自启；boot_resume 工具
  保留但**未安装任务**（用户裁定不自动恢复）。
- L3 clear-on-recover：代码+`tests/test_l3_alert_clear_v1.py` 4 项；09:47 残留 machine_alert 已清
  （history 备份 `fleet_heartbeat.machine_alert.history_20261026_0947`）。
- 计数精确性：probe exact（dup/extra 报警；dummy 不计数）`tests/test_fleet_probe_exact_v1.py` 3 项。

## 4. 回滚
- 窗失败：停 WMI 启动的进程（PID）→ WMI 重启→health PASS；bat 备份 `.ukemi_backup`（UKEMI 专用）
  不影响加固窗；AR 改动均为代码/工具，无 env 变更（除既有 bat stall 600）。
