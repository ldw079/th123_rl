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

## 2026-10-26 追加裁定
| 时间 | 决策 | 依据/理由 | 执行 |
|---|---|---|---|
| 11:00 | BC 锚 apply 用 **A：--no-dedupe**（保留 509 行） | X 去重会删 89% 补标签行；标签价值不以去重行数衡量 | 包§8/§3；10-27 10:30 部署 |
| 11:32 | **task-74 暂缓**（人类数据只分析不训练） | 地基(task-70/71/72)稳前不盲目学习；BC 锚反复重构教训 | task-74 backlog；task-70 仍只读 |
| 12:20 | H1 延迟 scope：CPU-only 优化后 T16 p99≤20ms/T32≤30ms | 本机 torch 2.14+cpu，无 GPU；KV cache 后 T16 9.85/T32 12.34ms | 原型继续；量化弃用 |
| 12:14 | C 盘清理（4.55→13.33GB，仅旧 temp/pip cache） | 加固窗需要 C≥6GB | 已执行，未碰模型/BC/备份 |
| 12:22 | UKEMI 样本门 70min/≥2帧档/受身≥25 | auditor 复核 | 明日 11:30 窗前 |
| 15:21 | 加固窗 AR-9a/9b/stall 通过；helper watcher 引号匹配 bug 修复 | AR-9a 首跑失败根因；R17-12 演练发现 | helper regex/校验修复；重跑证据 |
| 15:32 | P1-1 probe ctl 误计复现：AR dummy 测试进程 `python -c ... dummy_fleet_marker learner_hub/actor_worker` 与 control marker 进程含 `th123_rl_control` 被 ctl 查询计数（瞬态 ctl=4） | 修 probe: 排除 `dummy_fleet|ar6dummy|stopclean_marker`、ctl 期望精确 2/超缺报警；行为测试覆盖 dummy 不计/超数报警 | 已修 |

| 15:33 | P1-2 powercfg：**UIBUTTON_ACTION=0 语义=睡眠（非"不动作"）**；LID/PBUTTON 隐藏项 setac/dc 命令 rc=0 但 query 无输出；**"不动作"值/GUID 待查、未验证**；不得写"已置不动作" | 用户要求按钮/LID=0 | 已执行+记录 |
| 15:33 | P1-3 crash dump：`crashdump_config.py --apply` 非管理员 PermissionError；当前 DedicatedDumpFile/DumpFileSize=null、pagefile 仅 D:16GB → kernel dump 不可配置；**未实测**（不伪造） | 15:00 窗证据要求 | 如实记录 |

| 21:29 | BC 指针窗优化：gen2 提前构建（训练中），窗内仅 env 切换+WMI（≤10min） | 避免窗内 20GB copy/replace 锁风险 | c_gen_build/verify+TH123_BC_DIR；明日 13:00+ |
| 21:17 | 清理失败窗 staging（21.8GB），保留 backup_deploy 18.9GB；D 58.87GB | 磁盘压力 | 已执行；生产 trio 未动 |
| 21:03 | 加 TH123_EP_KEEP=300（learner 归档 episodes_keep） | H1/H2/task-74 需要数据 | 已实现+7项测试 |
| 21:26 | H1 三行 demo：MLP0.196/GRU0.692/TT0.644（7ep，仅协议，不下结论） | 数据量不足 | 明日 retention+oracle 正式三行 |
| 07:56 | **用户要求提前重启训练**（覆盖工作日 09:30 常规；用户明确指令） | 用户令 | 07:59 WMI morning_start 启动；health PASS；retention 生效 |
