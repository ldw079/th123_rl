# D1' Fleet 接管主训练 · 点火手册（runbook）

> 依据: 主规划 D1'（用户裁定 2026-10-06: 永久纯本地）+ 从零#2 修复波 + round16 U-1。
> 前提状态: fleet 全链修复已过 21/21 协议测试、144+1 变异拦截、一步等价探针 6/6。
> 本手册把点火收敛为"一次决策 + 两条命令"。

## 0. 前置检查（点火前 5 分钟）

```bat
cd %USERPROFILE%\Desktop\workplace\th123_rl
D:\temp\pyenv\python.exe -X utf8 test_fleet_protocol.py      :: 须 21/21
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py     :: 须 0 FAIL
```

- 磁盘 ≥ 2GB（learner disk_guard 会降级但别触发）。
- 确认无残留 fleet 锁: `D:\temp\th123_models\fleet\*.lock`（有则查 PID 死活后删）。

## 1. A/B 对照期（推荐首跑形态）

fleet 与单实例并行互相隔离（learner 默认 `--suffix _fleet`，不碰生产档），
用于同窗对照吞吐/胜率，**但 CPU 翻倍**——建议缩配：

```bat
:: 单实例训练照常跑; 另起缩配 fleet(2 actor/角色):
D:\temp\pyenv\python.exe -X utf8 -u fleet_supervisor.py --actors 2
```

- 观察窗: 12-24h。看 `D:\temp\learner_*.log` 的批更新耗时与陈旧度、
  actor 日志的局/小时。
- 对照判据(D1' 验收): learner 更新耗时回到安静机量级;
  fleet 吞吐(局/h, 折算满配) ≥ 单实例 2×。

## 2. 正式切换（验收通过后）

1. 停单实例: 先杀 `run_parallel.py`（父监督器, 防旧代码复活）→ 再杀三个
   `train_tm.py` → 游戏实例自清。
2. fleet 全量接管(空 suffix 写主档, 3 learner + 每角色 2 actor):

```bat
D:\temp\pyenv\python.exe -X utf8 -u fleet_supervisor.py --actors 6
:: 切换日如需带 learner 空 suffix: 逐角色 python learner_hub.py --char X --suffix ""
:: (supervisor 默认 suffix=_fleet; 全量迁移时改 supervisor 启动命令里的 learner 参数)
```

3. 回退路径: 停 fleet(CTRL-C, actors 先退) → 原 `run_parallel.py 5000`
   一键回单实例（模型/计数/难度档全在盘上, 无损回退）。

## 3. 点火首日检查单

- [ ] learner 日志出现 `批N局/... vK |KL|...`（批更新在走）
- [ ] `fleet/episodes/` 残留数有界（队列滞后仪表）
- [ ] `fleet/snap_{char}/version` 单调增
- [ ] actor 无 `快照等待超时`
- [ ] CPU: 满配 6 actor 时若 >90% 持续, 降回 4（D2' 容量阶梯再标定）
- [ ] 24h 后: `com_difficulty` 档、池快照、蒸馏行是否随 fleet 路径正常落盘

## 4. 已知护栏（本手册写作时已在位）

learner 单实例锁 / episode 失败隔离区 / disk_guard 角色过滤+数值序 /
快照版本单调地板 / 池根接线(FLEET_DIR/pool) / COM 难度档按 actor 隔离 /
首局 deck 入构造 / fleet 车道放行 / Ctrl-C actors 先退。
