# 事故 Postmortem: 主臂全灭（2026-10-26 00:43，P0；R17-12 重开）

> 状态：**已恢复**（01:13:41 WMI 启动，01:15:12 全启）；根因证据链见 §2；预防 §4。
> 影响：主臂（supervisor+3 learner+3 actor+3 游戏）00:43:10→01:15:12 约 **32min** 全灭；
> control 臂（25372/9856/21080）存活；v8 数据分段作废。

## 1. 时间线（实证）
| 时间 | 事件 | 证据 |
|---|---|---|
| 00:41:59 | 我的健康检查：hb 2s、无 alert、3 learner/3 actor/4 games | 该次命令输出 |
| 00:42:58 | merge dry-run（只读 npz，不碰游戏/进程） | 命令输出 |
| 00:43:01 | **fleet_heartbeat 最后一次写入** | hb mtime |
| 00:43:07 | 我 git commit/push 完成、回合结束 | git 输出/HEAD |
| **00:43:10-11** | **supervisor/learners/actors/主游戏全部消失** | actor 日志停更时间 |
| 01:13:16 | Lead 报 P0（仅 control 臂存活；hb 停 30min） | Lead 消息 |
| 01:13:41 | 我 **WMI** 启动 `cmd /c D:\temp\train_batch_launch.bat` | WMI 返回 ret=0 |
| 01:15:12 | 全启：supervisor 26012、learner 3208/19572/23072、actor 19924/24644/35448、games 21000/21010/21020/21080 | main_detached.log |
| 01:16:14 | hb 恢复（age 4s）、无 alert | 实测 |

## 2. 根因（证据链）
**直接原因：启动方式使 fleet 成为"工具后台作业"的子孙进程；我的回合结束（00:43:07）时
harness 清理仍在运行的后台作业，进程树 kill 把 fleet 一并杀死（00:43:10）。**

证据：
1. 23:30 监督修复窗由 `D:\temp\supervisor_fix_window.ps1` 执行，脚本内用
   **`Start-Process`** 启动 supervisor → supervisor 是 **PowerShell 后台作业的子孙**；
   learners/actors/games 又是 supervisor 的子孙。
2. 该窗口作业在 harness 后台一直显示 **running**（23:50 仍在）；我 00:43:07 回合结束后，
   harness 清理后台作业（`job_list` 之后为空）→ 进程树 kill 级联到 fleet。
3. **control 臂存活**：它是 23:15 由 **WMI**（`cmd /c launch_control_actor.bat`，父=WmiPrvSE，
   父退后孤儿化）启动，不是工具 shell 子孙 → 免疫。
4. supervisor console **无 Traceback/退出码**（被 SIGKILL/树杀，非自身异常）；无 python 应用错误；
   无电源事件（control 臂活着）。
5. 恢复用 **WMI 启动 bat**（train_start → supervisor 父进程已退出=孤儿化），此后无后台作业，
   结构上免疫同类清理。
6. 排除项：00:43 我没有运行任何 kill 命令（00:41:59 健康检查、00:42:58 只读 dry-run、00:43:07 git）；
   00:37/00:38 的 kill-by-name 只针对 th123.exe 且发生在 5min 前，当时 hb 仍 2s（非直接因）。

## 3. 次因/风险（我的操作）
- 00:37/00:38 我用"kill 所有非 21000/21010/21020/21080 端口的 th123"清理 anchor 临时游戏，
  误杀了 reimu actor 的 fallback 端口游戏（21002）→ reimu actor 重启（未致命，但暴露
  **kill-by-name/端口白名单脆弱**）。
- 长期用 `Start-Process` 启动常驻进程（fleet）而非 WMI detached —— 本次致命。
- 窗口脚本未做"父链 detached"校验。

## 4. 预防（立即执行）
1. **常驻 fleet 只用 WMI 启动**（`Win32_Process.Create` → `train_batch_launch.bat`），
   禁止从工具 shell `Start-Process` 启动 supervisor/learner/actor/game；
   新增 `tools/fleet_launch_wmi.py` 统一入口。
2. 窗口脚本（UKEMI/演练/迁移）启动段改为 WMI；脚本结束不保留后台作业；
   启动后校验 supervisor 父进程为 **gone/WmiPrvSE**（detached 不变量）。
3. **禁止 kill-by-name**：清理只按"已知 PID/端口+父链核对"；游戏端口白名单改为
   "父进程=本 fleet actor"。
4. 心跳扩展：learner/actor 进程数、max log age、supervisor 自身 PID；缺员>120s 机器告警
   （本次 auditor 人工发现，无自动告警）。
5. window 前置检查：detached 父链检查；window 后不得有运行中的工具后台作业。
6. R17-12 重开：本事故闭环（postmortem+decision log+预防落地+15:00 演练）前不得进 W4/Gen-2。

## 5. 恢复记录
- 01:13:41 WMI `cmd.exe /c D:\temp\train_batch_launch.bat`（ret=0）
- 01:13:56 league 分配；01:14:12/32/52 三 actor 起；01:15:12 全启
- 进程：supervisor **26012**（父已退，孤儿化）、learners **3208/19572/23072**、
  actors **19924/24644/35448**、games 21000/21010/21020/21080；
- 启动证据：`[前置] BC库宽度×3 OK`、`[exec] hitmem=24` ×3、learner 初始快照；
- hb 01:16:14 恢复、无 alert；control 未动（25372/9856）。
