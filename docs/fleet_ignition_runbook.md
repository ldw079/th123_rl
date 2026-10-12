# D1' Fleet 接管主训练 · 点火手册（runbook）

> 依据: 主规划 D1'（用户裁定 2026-10-06: 永久纯本地）+ 从零#2 修复波 + round16 U-1。
> 前提状态: fleet 全链修复已过 21/21 协议测试、144+1 变异拦截、一步等价探针 6/6。
> 本手册把点火收敛为"一次决策 + 两条命令"。

## 0. 前置检查（点火前 5 分钟）

```bat
cd %USERPROFILE%\Desktop\workplace\th123_rl
D:\temp\pyenv\python.exe -X utf8 tests\test_fleet_protocol.py      :: 须 24/24 (R63 起)
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py     :: 须 0 FAIL / 0 WARN
```

- 磁盘 ≥ 2GB（learner disk_guard 会降级但别触发）。
- 确认无残留 fleet 锁: `D:\temp\th123_models\fleet\*.lock`（有则查 PID 死活后删）。
- **R63 前置（重要）**: 盘上 `fleet/episodes/` 里 schema=v1 的旧局无法被
  新 learner 消费（会拒收并整队移入 `failed/`，然后 exit 1 等重启）。
  点火前先归档：

```bat
:: 旧代际 episode 归档(不删 — 保留证据); 路径按角色/后缀
move D:\temp\th123_models\fleet\episodes\*.npz D:\temp\th123_models\fleet\episodes\legacy_r62\
```

- **R63 前置（模型代际）**: learner 现在校验"模型档宏数 == 当前代码宏数"，
  不符即拒绝启动。若宏库在停机期间变更，必须先迁移/重训模型档，
  不要用旧档续训（`model_ppo_*_fleet.npz` / `macro_counts_*_fleet.npy`）。

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
:: R63 起 --suffix "" 与 _fleet **已完全隔离**(快照/队列各走自己的目录):
::   _fleet → fleet/snap_<char> + fleet/episodes          (现网路径不变)
::   ""     → fleet/snap_<char>_main + fleet/episodes_main (迁移用, 互不踩)
::   两个后缀可同时对同一角色运行(锁本就按 suffix 隔离)。
```

3. 回退路径: 停 fleet(CTRL-C, actors 先退) → 原 `run_parallel.py 5000`
   一键回单实例（模型/计数/难度档全在盘上, 无损回退）。

## 2b. 运营窗口制（C1-2, 用户裁定 2026-10-12）

- supervisor `--hours 9:00-23:00`：窗口尾自动干净收队（actor先退→learner存档）；
- 任务计划程序 `th123_fleet_window` 每日 09:00 自动拉起满配
  （`schtasks /Query /TN th123_fleet_window` 可查, 删除用 /Delete）;
- CPU 红线（R14）看门狗滚动均值降容后**只降不升** — 次日窗口头自动以满配重启即恢复；
- M1 的"48h 连续"口径 = **48h 累计运营窗口**（占空比日报：`tools/throughput_report.py`）。

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

## 5. R63 新增护栏（2026-10-07 架构审查修复）

| 护栏 | 语义 |
|---|---|
| **episode 尺寸代际契约** | 每个 episode 携带 `n_out/n_side/n_macros/feat_dim/code_n_macros`；写者落盘前自检、读者按**代码侧**宏数校验；不符者拒收+隔离+learner 响亮退出（原：形状错→批批量隔离→无限 continue=看起来在跑实际零学习） |
| **learner 模型代际校验** | `模型档宏数 != 当前代码宏数` → 拒绝启动（原只与"自己刚载入的档"自洽） |
| **快照/队列按 suffix 隔离** | `_fleet` 走原路径；其余 suffix 独立子目录（原：锁隔离但目录共享=互删数据） |
| **池清理前缀分流** | learner 不再删 `exploit_*` 快照（原：周期删掉剥削者的针对性对手） |
| **GPU 加载拒绝缺失参数** | 缺值档/缺子网络 → 抛错（原：只打印→**随机 critic 被发布**并驱动 30% 的价值引导决策） |
| **孤儿回收整树** | `taskkill /F /T` 连游戏子进程一起回收（原：只杀 worker，游戏残留占端口） |
| **actor 视为长期生产者** | 传大预算 `ACTOR_EPISODES`；exit 0 也重启（原：跑满 1000 局即被移出车队→静默排空到零 actor） |
| **镜像只翻水平轴** | `keys_to_input(mirror=True)` 只翻 H（原连 V 一起翻→朝向左时约一半决策执行纵向镜像动作） |
| **对手技能槽位越界钳制** | id≥112（patchouli 112-114）不写槽位+计数告警（原：IndexError→局被丢弃+重建） |
| **奖励仪表分栏** | 打印区分"诊断(不入回报)"与"入账"，小计只累计真实通道（原：幻影项 dmg/taken 混入"总和"、真扣分项 micro_tax 缺失） |

配套断言：`tools/contract_check.py` 的 R63 组（14 条）+ 行为测试
`test_mirror_axis_r63.py` / `test_contract_r63.py`（已入门禁 C15 列表）
+ `tools/gate_selftest.py` 的 R63 配对变异（增量子集: `SELFTEST_TAGS=R63`）。
