# 事故记录：drill 后 supervisor 心跳空窗（2026-10-27 10:24–10:28）

## 现象
- 10:24 BC 指针 drill：helper 停 main/control/watcher → WMI 重启（10:24:49）。
- 新 supervisor PID **18880** CreationDate **10:25:07**；`fleet_heartbeat` mtime **10:24:25**（旧 sup 最后一拍），
  直到 **10:28:02** 才更新 → 空窗约 **3.5min**；期间 `fleet_health --check` FAIL 仅 `hb_age>120s`
  （进程 3L/3A/ctl2/games4 均在）。
- 10:28 后 heartbeat 正常；10:28–10:29 health PASS。

## 根因（预期 boot 行为，非 bug）
- supervisor 启动先 **错峰拉起 learners（3×5s）+ actors（3×20s）+ 等待 games/健康**，之后才进入监督循环；
  循环内 `HEARTBEAT_EVERY` 拍才写心跳（10s/循环，首拍在 boot 完成后约 3 循环）。
- drill 的 `train_start --stop` 优雅停旧 sup（心跳停），新 sup boot 期无心跳 → 空窗。
- 该空窗会让 `hb_age>120` 报警，但 `critical_snapshot` 不因 hb_age 触发 AR 重启（仅 alert），未造成误恢复。

## 处置
- 10:40/11:10 两次稳定复查（hb_age<60、health PASS、4 游戏/3L/3A）；两次 PASS 后放行 BC 列签。
- **改进提案（窗后）**：supervisor boot 开始即写一拍 `write_heartbeat()`（避免重启后假 P1）；
  或在 health 中把"sup 进程 alive + 刚启动 <5min"标 boot 窗口不判 hb stale。需测试+gate 后实施。
- 记录：本事件属预期 boot 空窗，不作为 bug；但 WMI 重启后 3min 内 P1 误报需在窗后优化。

## 硬证据补充（2026-10-27 10:41）
- **旧 sup/进程停止**（`D:\temp\train_stop_clean.log`）：drill helper `--live` 于 **10:24:30** 发起停
  （PID 列表 main 20148/6188/23340/16928/24056/19976/1252，control 26788/12696，watcher 22924，games 4），
  watcher 10:24:31、control 10:24:32/34 被杀，10:24:44 done；旧 hb 最后 **10:24:25**（与停止时刻对齐）。
- **新 sup boot 日志**（`D:\temp\main_detached.log`）：**10:25:07** league 周期开始 →
  learners 10:25:08/13/18（5s 错峰）→ actors 10:25:23/43/10:26:03（20s 错峰）→
  **10:26:23 "全部启动 — 监督模式" + 看门狗 ON** + offline-gap 报告；
  首次新 heartbeat **10:28:02**（进入监督循环后约 99s，循环 10s×HEARTBEAT_EVERY=3 与首次调度/采样延迟）。
- **代码位置**：`fleet_supervisor.py` line 231 `HEARTBEAT_EVERY = 3`（每 3 循环 30s）；
  line 1085/1094 `write_heartbeat` 调用；监督循环 line 1060 `while ...: time.sleep(10)`；
  boot 错峰 line 1030–1038（learners STAGGER 5s / actors 20s）。→ boot 期无心跳为**预期行为**。
- **D/EP_KEEP**：`TH123_EP_KEEP=300` 为 **per-char 上限**（非全局）；当前 keep 计数
  reimu/marisa/suika=**148/148/103**（总 399，上限 900）；D **35.86GB**；
  BC 成功后清 backup 18.9GB→~55GB，再 `EP_KEEP=900`。
