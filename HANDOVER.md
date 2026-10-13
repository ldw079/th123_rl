# TH123 对战 AI 项目交接文档

> 日期: 2026-10-08 · 2026-10-11 对账修订(§五门禁数字/§七训练状态按实盘校正, 见 METHODOLOGY 2.64) · 供下一个智能体直接接手
> 读完本文即可开始工作; 细节按需查阅引用文档。

---

## 一、项目是什么

用强化学习(PPO + 宏动作)在真实游戏进程内训练东方非想天则(th123)的对战 AI，
目标超人水平。游戏通过 mod(SokuAITrainer) 的 TCP 锁步协议与 Python 通信。

**两条最高教义**:
1. 非想天则是 **62 帧游戏**(帧↔秒一律 /62, 禁 60)
2. **用户报告的观察是地面真相**(模型指标再好也盖不过用户看到的实际行为)

## 二、环境

| 项 | 值 |
|---|---|
| Python | `D:\temp\pyenv\python.exe`(3.12, 便携) |
| 游戏 | `D:\touhou\hisoutensoku2026-06-15\th123_train`(独立目录, 最小 mod 集) |
| 模型存储 | `D:\temp\th123_models\` |
| 仓库 | `%USERPROFILE%\Desktop\workplace\th123_rl\` |
| Git | PortableGit 2.56.0 at `D:\temp\PortableGit`(PATH 已持久化) |
| OS | Windows 10 x64 |

## 三、核心文件(改代码前必读)

| 文件 | 作用 | 何时改 |
|---|---|---|
| `METHODOLOGY.md` | **宪法** — 一切规范/变更/实验的制度文档 | 完成任何波次后追加版本条目 |
| `AGENTS.md` | 入口路由 — 通道/门禁/红线速查 | 通道结构变化时更新 |
| `train_tm.py` | 主训练器(单角色) | 奖励/宏/门控/对手轮换 |
| `feat_builder.py` | 特征构建(CORE_DIMS=330) | 特征段变更 |
| `ppo.py` | numpy PPO(数学层) | 损失/优化器/GAE |
| `ppo_gpu.py` | torch PPO(fleet learner 用) | 与 ppo.py 语义对齐 |
| `macro_executor.py` | 统一宏执行器(train_tm+side_driver 共用) | 宏执行逻辑 |
| `frame_events.py` | 帧级事件检测+反应掩码 | 事件/反应规则 |
| `side_driver.py` | 对手侧推理驱动(评估+自对弈) | 对手行为 |
| `tm_env.py` | 游戏环境(TCP 协议/进程管理) | 环境重建/协议 |
| `deck_sampler.py` | 卡组采样(含 C 对抗性卡组池) | 卡组生成逻辑 |
| `exploiter.py` | D4 剥削者(专打主策略弱点) | 剥削者行为 |
| `fleet_supervisor.py` | fleet 监督器 | 进程管理 |
| `learner_hub.py` | fleet 中央 learner | 批更新逻辑 |
| `actor_worker.py` | fleet 采集进程 | episode 序列化 |
| `episode_core.py` | episode npz 契约 | 数据格式变更 |
| `tools/contract_check.py` | 契约门禁(改代码后必须过) | 断言维护 |
| `tools/gate_selftest.py` | 变异自检(断言可证伪性) | 变异定义 |

## 四、训练操作

```bat
:: 启动(fleet 3 actor + reimu 剥削者)
启动训练.bat

:: 停止
停止训练.bat

:: 全量审计(健康/红线/日志/COM难度/fleet状态)
审计.bat

:: 流派实测(4模式: L1流派/L2必杀/L3逐SC/L3系统)
流派实测.bat
```

手动命令等价:
```bat
D:\temp\pyenv\python.exe -X utf8 tools\train_start.py --mode fleet --actors 3 --exploiter reimu
D:\temp\pyenv\python.exe -X utf8 tools\train_start.py --stop
D:\temp\pyenv\python.exe -X utf8 tools\audit_all.py
```

## 五、门禁(改代码后必过)

```bat
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py
```

- 当前: **567 PASS / 0 WARN / 0 FAIL**(2026-10-11 实测)
- 门禁不过 = 不许提交
- 变异自检(可选但推荐): `SELFTEST_TAGS=<标签> python tools/gate_selftest.py`

## 六、当前系统架构(2026-10-08 快照)

```
fleet_supervisor.py --actors 3
  ├── learner_reimu / learner_marisa / learner_suika  (ppo_gpu 批更新)
  ├── actor_reimu_0 / actor_marisa_1 / actor_suika_2  (train_tm 组合复用)
  └── [外部] exploiter.py --char reimu --fleet        (D4 剥削者)

数据流: actor 写 episode npz → learner 摸批 → GPU 更新 → 快照发布 → actor 轮换载新
```

**维度**: CORE_DIMS=330(316+14 风格段), 三角色宏数 70/76/77, n_side=680/710/715, league17新角色各70宏

**关键机制(按重要度)**:
- **D3' league20 对手生态(R65)**: 对手周期27位(主角色块×3交错+league17静态种子+COM); seed_league_pool 点火自愈
- **R62 胜负挂钩**: 败回合追扣 70% 微收入(擦弹+规避)
- **C 对抗性卡组池**: 四层逐卡加权(流派→必杀→SC→系统卡)
- **B 风格估计器**: 对手已出卡差分 → 14 维风格特征
- **B2 帧级事件**: E_OPP_STARTUP/E_NEAR_MISS/E_AIRTECH → 反应掩码 → 策略决策
- **D4 剥削者**: 镜像锁死打主策略最新快照, exploit_ 前缀入主池

## 七、当前状态

- **训练**: **运行中** — 2026-10-11 21:22 起带 **20 角色 league 对手生态**(D3'/R65: 对手周期 27 位 = 主角色块×3 交错 + 17 league 静态种子 + COM; fleet 3 actor + reimu 剥削者)。当日早些时候完成 train_start 自杀 bug 修复后恢复训练(20:22 首启)
- **D3'(R65)观察项**: 首个 league 位命中在 ep50≈4h(sakuya 位); overnight 后查 league 对局胜率(vs init_fresh 随机网应显著>50%)与 league 重算行的新角色标签累积
- **点火后健康读数**: learner 首批 17.7s/批(安静机量级)/快照滚动/KL 0.09-0.16/陈旧≤2; episode 正常流入
- **R63 修复已生效**: 10-08 20:18 fleet 重启载入 R63 后代码(随 04499b2 入库), 该轮 episode 零 failed
- **上轮末期读数**(10-08 22:46 league 重算): COM 0W-16L(主策略全胜) / 剥削者快照 0W-5L(gauge 健康) / 镜像对手 0W-7L
- **F6 新基线**(10-11, R63 后语义): reimu 弱侧(vs marisa 1-3, vs suika 0-4); 全对局顶时判定 = 双模型侧被动不接敌
- **观察项**: R62 相关性回正 / B 风格段活性 / C 流派战绩收敛 / 剥削者 gauge / **B3 远程弹幕涌现**(48h 钟起点 10-11 20:22, 工具 tools/remote_usage_report.py) / **系列预测阶段0**(learner 日志 grep"系列曲线", 位置分桶 aux/胜率基线, METHODOLOGY 2.69; 初读平坦→阶段3优先待 48h 确认, 方案 docs/_plans/series_opponent_prediction_plan_2026-10-06.md)
- **已知问题**: th123.exe 偶发 "pure virtual function call" 崩溃(游戏级, actor 自动恢复)

## 八、工作流

1. 用户给指令 → 读 `METHODOLOGY.md` 最新版本条目了解上下文
2. 改代码 → 跑 `contract_check.py`(必须全绿) → 提交 git
3. 训练相关变更 → 重启训练(`train_start.py`)
4. 定期用 `audit_all.py` 产出诊断报告

## 九、重要制度(METHODOLOGY.md 精选)

| 制度 | 内容 |
|---|---|
| 宏库 SOP | 新宏十步流程(宪法 §3.5) |
| 维度变更 | 改 CORE_DIMS 必须全链同步(模型+BC库+特征+门禁) |
| 贯通测试 | 新模块+新调用方成对落地必附集成测试 |
| 常量横扫 | 改 CORE_DIMS/N_* 后 grep 全库旧值 |
| 原子落盘 | np.savez 一律 tmp+os.replace |
| 单写者 | 共享档只由一方写(learner 写模型, actor 写 episode) |
| 62fps | 帧时间换算一律 /62 |

## 十、文档索引(按阅读顺序)

| 文件 | 何时读 |
|---|---|
| 本文(HANDOVER.md) | 接手时读一遍 |
| `README.md` | 仓库标准入口(快速开始/目录结构) |
| `METHODOLOGY.md` 尾部(最新版本条目) | 每次开工前扫最近 3 个版本 |
| `AGENTS.md` | 需要通道/门禁细节时 |
| `docs/master_plan_2026-10-05.md` | 了解任务全景与状态 |
| `docs/fleet_ignition_runbook.md` | fleet 点火/切换操作 |
| `docs/audit_protocol.md` | **审计前必读** — 审计三必要条件+标准清单(2026-10-12) |
| `docs/audit/` | 历次审计结论归档(按时间序, 最新一份看现状) |
| `docs/bugs/` | **bug 档案统一目录** — 制度(bug_protocol.md)+历次 bug 档(七字段), 挖出 bug 时必读 |
| `docs/_reviews/full_review_from_zero_2_2026-10-06.md` | 从零#2 全盘审计(从零#3 见 `docs/audit/`) |

## 十一、踩坑记录(新智能体必读)

| 坑 | 解法 |
|---|---|
| PowerShell 管道改文件 = GBK 读+UTF8 写 = 编码毁损 | 源码补丁一律走 Python io |
| `taskkill /PID X /T /Force` 的 `/Force` 在 PowerShell 里要 `/F` | 用 `/F` 或纯 cmd |
| bash `&` 后台任务随 shell 会话终止 | 用 `Start-Process`(Windows 持久化) |
| np.load 惰性句柄不关 = 自己锁自己 | `d.close()` 后再 `os.replace` |
| cmd 跨盘 cd 需 `/d` | `cd /d D:\...` |
| 改 CORE_DIMS 只改模型不改 BC 库 = actor 启动死循环 | 全链同步: 模型+BC+特征+门禁 |
| 旧 fleet 残留档是首要危险品 | 点火前清理: `_fleet` 模型/池快照/episode |
| safe-path 模式下 sys.path[0] ≠ 脚本目录 | 模块顶部 `sys.path.insert(0, HERE)` |
| **行为测试的副作用以生产为假想敌** — test_trainstart_cleanup 执行真实清理, 只排自身PID → "fleet运行中跑门禁"即灭队(R64后四次, 曾误诊主机停机) | 测试先探活fleet, 在场即跳过破坏性阶段(教训×4) |
| 门禁命令接管道(tail/grep)会吞退出码 — `${PIPESTATUS[0]}`或裸跑判绿, 红门禁禁止提交(f4668e1事故) |
| **锁的 PID 复用误判** — OpenProcess 对任何占用该 PID 的进程都成功, 被灭进程的 PID 被回收 → 假"已有实例"重启循环/假"拒绝双开" | 存活校验追加命令行匹配(learner/supervisor 锁同款, R67b) |

---

*本交接文档覆盖 2026-10-08 为止的全部工作; 2026-10-11 对账修订了门禁数字与训练状态(METHODOLOGY 2.64)。METHODOLOGY.md 是唯一权威 — 与本文冲突处以宪法为准。*
