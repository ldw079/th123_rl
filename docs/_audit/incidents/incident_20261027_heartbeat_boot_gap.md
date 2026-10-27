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
