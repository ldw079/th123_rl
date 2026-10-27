# 2026-10-28 晨间 runbook（host 时间）

> 顺序：09:25 启动 → 09:35 预哈希 → 09:45 BC 指针窗（≤10min）→ 成功后清理/EP_KEEP→ 10:15 UKEMI 前置 → 10:30–11:40 UKEMI → 11:45 观察。
> 不自动开窗；每窗单变量；失败立即回滚。BC 预列签已过（auditor），本 runbook 为执行清单。

## 0. 前置（09:20 前）
- 查 D≥35、无锁、无残留 training/lab 游戏；`health` 应 FAIL（未启动）→ 正常。
- 确认 gen2 `D:\temp\bc_gen2_20261027` 三 char/manifest 在；生产 trio 未动；`bc_backup_deploy_20261027` 在。

## 1. 09:25 启动训练
- WMI 启动 `D:\temp\train_batch_launch.bat`（当前 bat 无 `TH123_BC_DIR`，env 仍为 FEAT_SPACE/GEN2/...）。
- health 等待 PASS（sup1/3L/3A/ctl2/games4；boot 首拍已修，仍给 ≤5min）。
- 记录 PID/health/时间。

## 2. 09:35 预哈希
```bat
D:\temp\pyenv\python.exe -X utf8 tools\bc_gen_verify.py --dir D:\temp\bc_gen2_20261027
```
- 记录三 char 行/宽/hash16/loader、D、health。

## 3. 09:45 BC 指针窗（≤10min）
- 执行 `D:\temp\bc_pointer_window.ps1`（锁→helper `--assume-locked`→readers=0→gen_verify→bat 行前插 env→WMI→health 120×5s→loader 证据→release）。
- 成功判定：health PASS 4 游戏、learner 日志 `BC loaded rows=429579/353791/329422 width=831/866/846 bc_dir=...`、无 alert。
- 失败：脚本 finally 恢复 bat+WMI+health；不重试 copy fallback；记录 incident。

## 4. BC 成功后（≤30min）
- 删 `bc_backup_deploy_20261027`（18.9GB）；D 回 ≥35。
- bat `TH123_EP_KEEP=220`（per-char），WMI 重启，health PASS；24h 监控（BC 加载/schema/aux/选择率/BH/whiff/KL/ent/冲突登记）。

## 5. 10:15 UKEMI 前置 / 10:30 窗
- 前置：预注册（10:30–11:40）mtime/0 残留；baseline `--minutes 70` v2+sha；watcher `--auto-recover`；锁；gate 761+。
- 10:30 开窗（`D:\temp\ukemi_window.ps1`）：env=1→WMI→≤10min→验收 dir/f、skip<10%、exec/reg>0.7、ent≥0.75、KL≤0.30、4 游戏、CORE=391、BC/池回退、schema、无 alert。
- 失败：env=0 单次重启，不留在停训；11:45 观察（≥1200/char）。

## 6. BC/UKEMI 后：clean-state limit 校准 + strict lab 重判（新 P0）
- 判据：**planned steps 全执行 AND comboLimit≥100**；damage/count 只作过程量。
- 字段：comboLimit=0x4B8、comboCount=0x4B4、comboDamage=0x4B6（原版 PID24260 已校；训练/lab 需同版本核）。
- 流程：每个宏前等 comboDamage/Count/Limit 清零 → 单次跑宏 → 采样 limit 曲线/最大 limit；记录偏移/版本一致性。
- 重判 50 lab：逐条 planned/executed/segments/hits/dmg/**max_limit**/count/pass(limit≥100)/reason；39/50、37/58 标 proxy 撤回。
- 若 limit 只能到 40：给帧证据/机制说明，标"不可实现"（路线/伤害/位置/对手状态/机制上限）。
- 修复目标：能出圈（limit≥100）；BC 锚/连段课程/选择信号同主线。
