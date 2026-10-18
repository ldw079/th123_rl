# CPU 红线防护加固方案（2026-10-18）

> **需求来源**: 用户 2026-10-18 12:0x「CPU的红线要立住，想办法完善防护机制」。
> **触发事件**: 12:00 用户报系统异常卡顿 — 施工变异 sweep（2 workers）在沙箱内并发跑 `contract_check`+行为测试（`test_r17_ppo` 单进程约 5 核）+ 沙箱 7.05GB 写盘，整机 CPU **85–100%**；而看门狗只量**训练族**（当时族口径 ~20–30%），红线**未触发**。Lead 终止 sweep+清沙箱后整机回落 49–53%。
> **定位**: R14（CPU≤75% 红线，用户明令）的**执行层加固**；不改 §0/§4 红线语义，只补"旁路重负载"的防护。编号 **CPU-H**（hardening）。
> 格式: PLANNING_AGENT.md 三段式（现状核验→可执行方案→验收途径）。

---

## 0. 现状核验（2026-10-18 12:00–12:10 实测）

| 件 | 现状 | 证据 |
|---|---|---|
| R14 常量 | `CPU_RED_LINE=75.0` / `CPU_WINDOW=6`（6×30s 滚动均值）/ `CPU_REENTER=65.0` | `fleet_supervisor.py:24-33` |
| 族口径 | `family_cpu_seconds()` 只统计**监督器进程树**；旁路（sweep/gate/bc_build/评估/对照臂）**不计入** | `fleet_supervisor.py:144-174` |
| 采样/动作 | 每 30s 采样一次；均值>75 → 暂停最新 actor；<65 满窗 → 恢复；全灭告警 | `fleet_supervisor.py:634-665` |
| sidecar | `fleet_heartbeat.wd` = `"ts family_pct"` 两字段；消费者 `status_dashboard.get_watchdog_status()` 只显示族 CPU | `status_dashboard.py:213-232` |
| 变异 sweep | `gate_selftest_parallel.py` 默认 **8 workers**（`:85`），无 preflight、无 worker cap、无优先级、无互斥；先跑一次基线门禁（沙箱内 `contract_check`，:99-133），再逐变异跑沙箱 | `tools/gate_selftest_parallel.py:85,99-160` |
| 旁路优先级 | 仅 supervisor 派生的 fleet 树设 BELOW_NORMAL；sweep/gate/bc_build 子进程继承**普通**优先级 | `fleet_supervisor.py:25`、`human_solo_collect.py:71-75`（仅此一处延伸） |
| 整机指标 | 无：`wd` 只写族口径；dashboard 无整机行 | 同上 |
| 本次事件量化 | 整机 85–100%（4 游戏+3 learner+3 actor+对照臂 2 进程 + sweep 2 workers×~5 核）；族口径 20.30%（`wd` 12:02 读数）→ 红线未触发；沙箱 1301 文件/7.05GB | Lead 12:01–12:03 实测 |

**结论**: R14 的**训练族红线**本身有效（且不应动），缺口在"**旁路重负载无闸门、整机无观测、无协作停止**"。psutil 在本机不可用（实测 import 失败）→ 整机 CPU 用 `ctypes.GetSystemTimes`（免依赖、免 subprocess）。

---

## 1. 方案（三层防护 + 一个闸门）

### L0 观测层（supervisor 增整机/旁路指标）
- `fleet_supervisor.py` 新增 `machine_cpu_pct()`（ctypes `GetSystemTimes`，Δidle/Δtotal；采样失败返回 None 哨兵）与 `aux_cpu_pct()`（`_wd_proc_rows` 过滤 `python.exe` 中非族、非对照臂的累计 CPU，Δ/Δ墙钟）。
- `fleet_heartbeat.wd` 扩为 **`ts family_pct machine_pct aux_pct`**（前两字段语义/顺序不变 → 旧读者按 `split()[1]` 取族口径不受影响；dashboard 改读 4 字段并容错）。
- `tools/status_dashboard.py`：CPU 看门狗行改为「族 x% · 整机 y% · 旁路 z%」，整机>85 显红。

### L1 训练红线（保持不变）
- 75/65、6 窗、可恢复暂停、全灭告警逻辑**一行不改**；仅回归验证（既有 `tests/test_fleet_watchdog_r74.py` 全绿）。

### L2 重负载闸门 `tools/load_gate.py`（新增，单一入口）
所有"重"任务必须经它启动：`gate_selftest_parallel` / `gate_selftest` / `bc_build` / `eval_matrix` / `audit_all`（首期接入前三个 + sweep）。

| 功能 | 规格 |
|---|---|
| 单实例互斥 | 锁文件 `STORE/heavy.lock`（json: pid/kind/start/workers/log）；stale 判定 = PID 已死 或 超 `HEAVY_LOCK_MAX_H=8h`；二次 acquire **拒绝并打印持锁者** |
| 注册表 | `STORE/heavy_jobs.json`（pid/kind/start/workers/log），退出清理；supervisor/dashboard/审计可读 |
| 启动前 preflight（≤8s） | 整机 CPU（3×1s 均值）> **55%** 拒绝；空闲 RAM < **6GB** 拒绝；训练族 CPU > **70%** 拒绝（让路训练）；夜间窗 **20:00–08:00** 自动放行，窗外需 `--allow-day` 显式标记 |
| worker 预算 | 子进程 priority = **BELOW_NORMAL**（0x4000）；`workers = max(1, min(requested, cores//8))`（18 核→2，硬上限 4）；`SELFTEST_TAGS` 增量任务也走同一 cap |
| 运行时监控 | 独立线程每 5s：整机 >**90%** 连续 3 窗（15s）→ 中止；训练族 >75% 连续 3 窗 → 中止（aux 让路）；空闲 RAM <3GB → 中止；中止=杀自身子进程树+清沙箱+写报告+释放锁 |
| 协作停止 | 监控 `STORE/heavy.stop`（json reason/ts，由 supervisor/Lead 写）：收到 → ≤10s 内优雅中止并留报告 |
| 采样轨迹 | 写 `STORE/heavy_runs/<ts>_<kind>.json`：起止/参数/每 5s 整机与族 CPU/中止原因 → 供审计与"整机 95 分位"验收 |

### L3 supervisor 旁路看门狗（每心跳，30s）
- 若 `machine>85%` 连续 3 窗 **且** `family<75%` → 写 `fleet_heartbeat.machine_alert`（含 reason + top 旁路 PID/名字）+ 日志 `!!ALERT!!` + 若存在 `heavy_jobs` 则写 `heavy.stop` 请求中止；**绝不自动杀 fleet**。
- 若 `machine>95%` 连续 2 窗 → 同上但立即（不等 3 窗）。
- dashboard 读 alert（红色行）；Lead 的 L1 心跳把该告警列入必查项。

### L4 接入与纪律
- 默认 workers 从 **8 → 2**（`gate_selftest_parallel.py:85`）；README/HANDOVER/AGENTS R14 行补"整机口径+闸门+夜间窗"。
- 纪律: 重负载一律夜间窗 + 分离进程 + 闸门；训练高峰禁止并行；禁连续重跑测试（今日事件教训入 METHODOLOGY §10）。

---

## 2 工作量 / 分阶段 / 回滚 / 制度对齐 / 风险 / 用户裁定项

**分阶段（每阶段独立可验收、可回滚）**
| 阶段 | 内容 | 人日 | 回滚 |
|---|---|---|---|
| **P-A（今晚 B1 前，必须）** | `load_gate` 核心（锁/注册/preflight/监控/协作停止/轨迹）+ `gate_selftest_parallel` 接入 + 默认 workers=2 + BELOW_NORMAL | 0.3 | 删新文件 + 还原 sweep 入口；env `TH123_LOAD_GATE=0` 旁路 |
| P-B | supervisor L0（整机/旁路指标+sidecar 扩字段+alert）+ dashboard 三口径 + L3 自动 stop | 0.5 | sidecar 前两字段不变可回退；L3 用 env 开关 |
| P-C | `bc_build`/`eval_matrix`/`audit_all` 接入 + 测试/变异 + AGENTS/HANDOVER/METHODOLOGY 文档 | 0.2 | 各工具入口 `try: gate; except ImportError: 原逻辑` |

**制度对齐**: 门禁新增断言 ≥2 条（wd 三字段/sweep 默认 workers=2）+ 配对变异 ≥2 条（锁校验失效→测试必红；stop 不响应→测试必红）；行为测试 C15 注册；**不改 R14 语义与 fleet 树策略**。

**风险表**
| 风险 | 概率 | 缓解 |
|---|---|---|
| 假阳性 auto-abort 打断正常 sweep | 中 | 阈值保守（90%×15s）+ 演练；abort 写报告可续跑 |
| 闸门锁 stale 卡死后续任务 | 低 | PID 存活+8h 双判 reclaim；`--force-unlock` 需打印证据 |
| supervisor 越权杀 fleet | 低 | **明确禁止**：L3 只停 aux、只写告警 |
| CIM 采样开销 | 低 | 整机用 ctypes；族口径沿用现有 30s CIM |
| 用户自有应用占机导致误判 | 中 | 只对注册的 heavy job 发 stop；无 heavy job 时仅告警 |

**用户裁定项（默认值已给，可改）**: ①闸门阈值（preflight 55% / abort 90% / 15s）；②夜间窗 20:00–08:00；③是否允许"用户自有重负载"也触发 aux stop（默认只停注册的重任务）。

---

## 3 验收途径（量化）

1. **行为测试**（新档 `tests/test_load_gate.py`，C15 注册，≥10 项）：锁互斥/持锁者拒绝、stale 回收、worker cap 派生（注入 cores）、preflight 三类拒绝（注入整机 80%/RAM 2GB/族 78%）、协作停止 ≤1 循环、注册表写清、priority 设置、轨迹 JSON、sidecar 三字段与旧两字段兼容。
2. **配对变异**（≥2）：①锁校验恒真 → 互斥测试必红；②stop 文件检查失效 → 协作停止测试必红；`SELFTEST_TAGS` 单跑逐条验证。
3. **演练（B1 夜间窗）**：注入合成负载（低优先级 spin 20s）→ supervisor `machine_alert` ≤15s 出现、`heavy.stop` ≤15s 写入、sweep abort ≤10s 且登记清理；合成负载移除后无残留。
4. **真实回归（B1 sweep 本体）**：sweep 必须经 `load_gate` 启动；轨迹 1s/5s 采样，**整机 CPU 95 分位 ≤85%**、无用户卡顿；如触发 abort，报告原因可追溯；结束后 `heavy.lock`/`heavy_jobs.json`/`gate_sandbox` 三者皆空。
5. **红线回归**：既有 `test_fleet_watchdog_r74` 全绿、`wd` 族口径读数与改动前同量级；门禁裸跑 0 FAIL（原始末行入提交）。

**排期与依赖**: P-A 今晚 20:00 前完成（B1 sweep 必须走闸门）；P-B/P-C 随 W2。依赖：无外部件；psutil 不可用已绕开。

---

## 4 不变面（防误改）

- 不自动杀/暂停 fleet、不改 75/65/6 窗逻辑、不改族口径定义（R170/R169 结论保持）。
- `fleet_heartbeat.wd` 前两字段语义不变；`fleet_heartbeat` 主文件格式不变。
- 不引入新第三方依赖（psutil 不可用；整机 CPU 用 ctypes）。
- 闸门默认失败**关闭**（缺锁/异常时拒绝启动重任务并打印原因，不静默放行）。
- 不改训练语义/奖励/特征/协议；不改 mod 与 C9 血统。

---

## 修订记录

| 日期 | 版本 | 说明 |
|---|---|---|
| 2026-10-18 | v1 | 12:00 卡顿事件驱动立档：现状核验（族口径盲区/8 workers 默认/无优先级/无整机指标）+ 三层方案（L0 观测/L2 load_gate/L3 旁路看门狗，L1 保持）+ P-A/B/C 分阶段 + 量化验收 + 用户裁定 3 项；P-A 今晚 20:00 前必须落地 |
