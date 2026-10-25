# 事故 Postmortem: marisa learner 停摆 78min（2026-10-25，P0；R17-12）

> 状态：**已部署并验收**（2026-10-25 23:30 监督修复窗：新 supervisor PID=6852、23:30:09 起、23:31:08 全启；live kill 7.3s；alert 已清；commit `0c4bec1`/`01316f4`）。**R17-12 条件通过**：⑤ 待明日 15:00 live 停滞演练 + auditor 核验。
> 影响：v8 2h/4h 中 marisa learner（21:57–23:15，78min）与 suika learner（23:07–23:28，21min）及 23:30–23:31 重启段作废；control 相关段按 auditor 分段标注。

## 1. 时间线（实证）
| 时间 | 事件 | 证据 |
|---|---|---|
| 21:57 | `learner_marisa.log` 最后更新 | 日志 mtime |
| 22:02:25 | supervision: `看门狗停滞 learner marisa — 精确重启` | `fleet_supervision.log` |
| 22:02→23:15 | **无 marisa learner 进程/无重启记录** | 进程表/日志 |
| 23:09:27 | marisa actor 退出(code=1)，23:09:57 自动重启 PID=17312 | supervision 日志 |
| 23:14 | auditor 发现 marisa learner 缺失、control actor 缺失 | 审计 |
| 23:14:56 | 手动恢复 marisa learner PID=33364（批 v2821 KL0.188） | restart log |
| 23:15:10 | 手动恢复 control actor PID=9856 + game 21080 | 进程表 |
| 23:15:31 | hb 2s、无 alert、4 游戏（+BC 补采 21103） | 监控 |

## 2. 根因（代码级）
- `fleet_supervisor.py` task-53 停滞看门狗处理路径（旧 889-901）：
  1) `watchdog_stalled()` 检测日志停滞；
  2) 处理循环 `pop` 出 `learners[ch]` / `actors[key]`，`_kill_tree(pid)`；
  3) **没有任何 spawn/放回** → 字典项被删除，后台进程死亡 → 监督器认为该 learner"已不存在"，
     正常死亡重启路径（轮询 `p.poll()`）也不会触发（已 pop）。
- 即"精确重启"实现只完成 kill，未完成 restart；与正常崩溃重启路径分叉（债务）。
- 为什么 actor 未消失：actor 走的是正常 `poll()!=None` 重启路径（未被 stall 看门狗命中，或命中的是
  learner）；control actor 缺失是独立问题（对照臂未纳入监督，boot 时未拉起/被清理）。

## 3. 漏检
- 心跳只写 supervisor 自身状态，**不含 learner 进程数/日志 age**；supervisor 存活 → hb fresh，
  外部监控看不出缺员。
- 停滞只写 `fleet_supervision.log` 的 ALERT 文本，未升级为机器告警（alert 文件/通知）。
- 门禁/审计不检查训练进程完整性（无 3 learner×3 actor + control 的运行期契约）。

## 4. 修复（已实现，未部署）
1. `fleet_supervisor.py`：新增 `_spawn_learner_proc(ch)`（boot/死亡重启/看门狗重生单一路径）与
   `restart_stalled(kind,key,...)`：**kill 后必须 spawn**，替换字典项，计数/时间戳更新，
   失败不掀翻监督器（记录日志）。
2. 停滞处理调用 `restart_stalled`；boot/死亡重启收敛到同一 spawn 路径（消除分叉债）。
3. 行为测试 `tests/test_fleet_watchdog_restart_v1.py`（C15）：
   - learner 停滞 → 真进程替换且存活（真实 subprocess）；
   - actor 停滞 → 替换/计数；
   - 真实旧日志 mtime 检测；
   - spawn 失败返回 None 不崩。
4. 待办（15:00 窗）：部署 patched supervisor（WMI 重启 supervisor → 会重启 actor/learner，需窗口）；
   control actor 纳入监督；心跳加 learner/actor 进程数+日志 age 告警。

## 5. 系统预防
- 心跳/监控：`fleet_heartbeat` 扩展字段（learner 数、actor 数、max log age）；缺员>120s 机器告警。
- 监督器不变量：启动后 60s 内 learner/actor 数必须达配置值；每 5min 自检。
- control 臂：独立 supervisor 或纳入主监督（actor+learner 同监控），避免"有 learner 无 actor"。
- 窗口前置检查：窗验收脚本检查 3 learner + 3 actor + control 臂进程/日志新鲜度。

## 6. 回归与闭环
- 回归用例已入 C15（真实进程/日志证据，非字符串断言）。
- R17-12 要求：本 P0 未完成 postmortem+decision log 不进入 W4/Gen-2 迁移；本文件即闭环节点，
  decision log 条目：2026-10-25 23:15 手动恢复 + 23:xx 修复（窗口部署待）。
- 后续同类根因（只杀不启/关键进程缺失未告警）复发 → 升级对应 AC。

## 7. 反债评估（R16）
- 修复统一 spawn 路径（boot/重启/停滞）消除"三条路径"债；不引入一次性补丁。
- 不再以"supervisor 存活=健康"作为判据；以进程完整性+日志新鲜度行为指标为准（R17-5）。
- 心跳/监督增强纳入 W1/W2 前的运维项；control 臂监督纳入监督器正式职责。

## 附: 同 bug 第二例（suika learner, 2026-10-25 23:20）
- 23:20:06 旧 supervisor 看门狗检测 `learner suika 日志312s未更新` → kill（无 spawn）→ suika learner 消失，主日志 age 811s。
- 23:28:31 手动恢复 PID=3472（初始 v2367、hitmem=24；输出 `learner_suika_restart.log`）。
- 结论：同一 P0 根因在 marisa（21:57→23:15）后再次发生；**修复代码已提交 0c4bec1 但运行中 supervisor 仍旧代码**，必须尽快重启 supervisor（窗）才能闭环。
- 第二例影响：suika learner ~23:07→23:28 约 21min 无学习；v8 数据标注作废段。
